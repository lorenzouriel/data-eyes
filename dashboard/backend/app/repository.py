"""
Trend-history repository client.

Talks to the dedicated repository database (dashboard/repository/init.sql)
— never to a monitored SQL Server. This is what makes trend charts possible
without Grafana's old (never-actually-running) Prometheus scrape pipeline,
and it follows DPA's real architecture: history lives in its own store, not
inside the systems being watched.

The connection pool is created lazily on first use, not eagerly at app
startup — a repository outage must never prevent the fleet/tab APIs (which
don't depend on it) from serving. See collector.py for the same resilience
pattern applied to the collection loop itself.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import asyncpg

from . import crypto
from .config import InstanceConfig, settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


class RepositoryUnavailable(Exception):
    """Raised when REPOSITORY_DSN isn't configured or the DB can't be reached."""


async def get_pool() -> asyncpg.Pool:
    """Every connection failure — unset DSN, unreachable host, refused auth,
    a Postgres that's mid-restart — normalizes to RepositoryUnavailable so
    every caller has exactly one exception type to handle, regardless of
    *why* the repository isn't available right now. Configured-but-down is
    the more common real-world case than never-configured; both must degrade
    the same way."""
    global _pool
    if not settings.REPOSITORY_DSN:
        raise RepositoryUnavailable("REPOSITORY_DSN is not configured")
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(settings.REPOSITORY_DSN, min_size=1, max_size=5)
        except Exception as e:
            raise RepositoryUnavailable(f"Could not connect to the repository database: {e}") from e
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def _acquire():
    """pool.acquire() returns a context manager — the actual connection
    attempt happens at its __aenter__, not here, so failure normalization
    lives in each caller's `async with await _acquire() as conn:` try/except,
    not in this function. This just gets a (possibly freshly created) pool."""
    return (await get_pool()).acquire()


def _invalidate_pool_on_failure() -> None:
    """Drop a pool that just failed mid-session (e.g. Postgres restarted
    after the pool was created) so the next call reconnects from scratch
    instead of retrying against dead connections."""
    global _pool
    _pool = None


async def insert_snapshot(
    instance_name: str,
    overall_severity: str,
    categories: Dict[str, str],
    metrics: Dict[str, float],
) -> None:
    """One row per category, plus a synthetic "overall" row so the Main Page
    fleet card can show an instance-level trend without picking one category
    to stand in for the whole instance."""
    captured_at = datetime.now(timezone.utc)

    rows = [(captured_at, instance_name, overall_severity, "overall", overall_severity, None)]
    for category, severity in categories.items():
        metric_value = next(
            (value for key, value in metrics.items() if key.startswith(f"{category}.")), None
        )
        rows.append((captured_at, instance_name, overall_severity, category, severity, metric_value))

    try:
        async with await _acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO metric_snapshot
                    (captured_at, instance_name, overall_severity, category, severity, metric_value)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                rows,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Snapshot insert failed: {e}") from e


async def prune_old_snapshots(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM metric_snapshot WHERE captured_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Prune failed: {e}") from e
    # asyncpg returns a string like "DELETE 42" — pull the row count back out.
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def get_trend(instance_name: str, category: str, since_hours: int = 24) -> List[Dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    try:
        async with await _acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT captured_at, severity, metric_value
                FROM metric_snapshot
                WHERE instance_name = $1 AND category = $2 AND captured_at >= $3
                ORDER BY captured_at ASC
                """,
                instance_name,
                category,
                since,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Trend query failed: {e}") from e
    return [
        {
            "captured_at": row["captured_at"].isoformat(),
            "severity": row["severity"],
            "metric_value": row["metric_value"],
        }
        for row in rows
    ]


async def insert_resource_rate(instance_name: str, category: str, metric_value: float) -> None:
    """Reuses metric_snapshot for the two Resources-tab metrics that are only
    meaningful as a rate (disk read MB/s, batch requests/sec — see
    app/collector.py). severity is fixed to "OK": these are informational,
    not operational-risk gates with a threshold band the way backup/CHECKDB
    are, so they're written outside fleet_health_score's rollup (same
    reasoning top_queries is already excluded from it)."""
    captured_at = datetime.now(timezone.utc)
    try:
        async with await _acquire() as conn:
            await conn.execute(
                """
                INSERT INTO metric_snapshot
                    (captured_at, instance_name, overall_severity, category, severity, metric_value)
                VALUES ($1, $2, 'OK', $3, 'OK', $4)
                """,
                captured_at,
                instance_name,
                category,
                metric_value,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Resource-rate insert failed: {e}") from e


async def insert_wait_category_snapshot(instance_name: str, category_seconds: Dict[str, float]) -> None:
    """One row per category this cycle — category_seconds is the delta
    since the previous cycle (see app/collector.py), already computed by
    the caller; this function just persists it."""
    if not category_seconds:
        return
    captured_at = datetime.now(timezone.utc)
    rows = [(captured_at, instance_name, category, seconds) for category, seconds in category_seconds.items()]
    try:
        async with await _acquire() as conn:
            await conn.executemany(
                "INSERT INTO wait_category_snapshot (captured_at, instance_name, category, seconds) "
                "VALUES ($1, $2, $3, $4)",
                rows,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Wait-category snapshot insert failed: {e}") from e


async def get_wait_category_history(instance_name: str, since_hours: int = 24) -> List[Dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    try:
        async with await _acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT captured_at, category, seconds
                FROM wait_category_snapshot
                WHERE instance_name = $1 AND captured_at >= $2
                ORDER BY captured_at ASC
                """,
                instance_name,
                since,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Wait-category history query failed: {e}") from e
    return [
        {"captured_at": row["captured_at"].isoformat(), "category": row["category"], "seconds": row["seconds"]}
        for row in rows
    ]


async def prune_old_wait_category_snapshots(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM wait_category_snapshot WHERE captured_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Wait-category prune failed: {e}") from e
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def insert_blocking_event(
    instance_name: str, root_sql: Optional[str], lock_type: Optional[str], blocked_count: int, duration_seconds: float
) -> None:
    try:
        async with await _acquire() as conn:
            await conn.execute(
                """
                INSERT INTO blocking_event
                    (instance_name, root_sql, lock_type, blocked_count, duration_seconds)
                VALUES ($1, $2, $3, $4, $5)
                """,
                instance_name,
                root_sql,
                lock_type,
                blocked_count,
                duration_seconds,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Blocking-event insert failed: {e}") from e


async def get_blocking_events(instance_name: str, since_hours: int = 24) -> List[Dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    try:
        async with await _acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT captured_at, root_sql, lock_type, blocked_count, duration_seconds
                FROM blocking_event
                WHERE instance_name = $1 AND captured_at >= $2
                ORDER BY captured_at DESC
                """,
                instance_name,
                since,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Blocking-event query failed: {e}") from e
    return [
        {
            "captured_at": row["captured_at"].isoformat(),
            "root_sql": row["root_sql"],
            "lock_type": row["lock_type"],
            "blocked_count": row["blocked_count"],
            "duration_seconds": row["duration_seconds"],
        }
        for row in rows
    ]


async def dismiss_advisor_finding(instance_name: str, finding_key: str) -> None:
    """Idempotent — dismissing an already-dismissed finding just refreshes
    dismissed_at, it doesn't error."""
    try:
        async with await _acquire() as conn:
            await conn.execute(
                """
                INSERT INTO advisor_dismissal (instance_name, finding_key)
                VALUES ($1, $2)
                ON CONFLICT (instance_name, finding_key) DO UPDATE SET dismissed_at = now()
                """,
                instance_name,
                finding_key,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Advisor dismiss failed: {e}") from e


async def get_dismissed_advisor_findings(instance_name: str) -> set:
    try:
        async with await _acquire() as conn:
            rows = await conn.fetch(
                "SELECT finding_key FROM advisor_dismissal WHERE instance_name = $1", instance_name
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Advisor dismissal query failed: {e}") from e
    return {row["finding_key"] for row in rows}


async def prune_old_blocking_events(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM blocking_event WHERE captured_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Blocking-event prune failed: {e}") from e
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Instance registry — database-backed fleet registry (Phase 2). Shares this
# module's pool/RepositoryUnavailable handling rather than owning a second
# one, since it's the same Postgres database as the trend snapshots above.
# ---------------------------------------------------------------------------

class InstanceNameConflict(Exception):
    """Raised by create_instance() when the name is already registered."""


def _row_to_instance(row) -> InstanceConfig:
    return InstanceConfig(
        name=row["name"],
        label=row["label"],
        environment=row["environment"],
        mssql_connection_string=crypto.decrypt(row["connection_string_encrypted"]),
    )


async def list_instances() -> List[InstanceConfig]:
    try:
        async with await _acquire() as conn:
            rows = await conn.fetch(
                "SELECT name, label, environment, connection_string_encrypted FROM instance ORDER BY name"
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Listing instances failed: {e}") from e
    return [_row_to_instance(row) for row in rows]


async def get_instance(name: str) -> Optional[InstanceConfig]:
    try:
        async with await _acquire() as conn:
            row = await conn.fetchrow(
                "SELECT name, label, environment, connection_string_encrypted FROM instance WHERE name = $1",
                name,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Fetching instance failed: {e}") from e
    return _row_to_instance(row) if row is not None else None


async def create_instance(
    name: str,
    label: str,
    environment: Optional[str],
    connection_string: str,
    created_by: Optional[str],
) -> InstanceConfig:
    encrypted = crypto.encrypt(connection_string)
    try:
        async with await _acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO instance (name, label, environment, connection_string_encrypted, created_by)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    name,
                    label,
                    environment,
                    encrypted,
                    created_by,
                )
            except asyncpg.UniqueViolationError as e:
                raise InstanceNameConflict(f"Instance '{name}' already exists") from e
    except (RepositoryUnavailable, InstanceNameConflict):
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Creating instance failed: {e}") from e
    return InstanceConfig(name=name, label=label, environment=environment, mssql_connection_string=connection_string)


async def update_instance(
    name: str,
    label: Optional[str] = None,
    environment: Optional[str] = None,
    connection_string: Optional[str] = None,
    clear_environment: bool = False,
) -> Optional[InstanceConfig]:
    """Partial update — only fields explicitly given are overwritten.
    `clear_environment=True` sets environment to NULL (distinct from
    "not provided", since environment is otherwise Optional[str])."""
    sets = ["updated_at = now()"]
    params: List[Any] = []
    if label is not None:
        params.append(label)
        sets.append(f"label = ${len(params)}")
    if clear_environment:
        sets.append("environment = NULL")
    elif environment is not None:
        params.append(environment)
        sets.append(f"environment = ${len(params)}")
    if connection_string is not None:
        params.append(crypto.encrypt(connection_string))
        sets.append(f"connection_string_encrypted = ${len(params)}")
    params.append(name)

    try:
        async with await _acquire() as conn:
            row = await conn.fetchrow(
                f"UPDATE instance SET {', '.join(sets)} WHERE name = ${len(params)} "
                f"RETURNING name, label, environment, connection_string_encrypted",
                *params,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Updating instance failed: {e}") from e
    return _row_to_instance(row) if row is not None else None


async def delete_instance(name: str) -> bool:
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM instance WHERE name = $1", name)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Deleting instance failed: {e}") from e
    return result != "DELETE 0"


# ---------------------------------------------------------------------------
# User accounts (Phase 3) — replaces the single shared DASHBOARD_ADMIN_
# USERNAME/PASSWORD credential. Same pool/RepositoryUnavailable pattern.
# ---------------------------------------------------------------------------

class UsernameConflict(Exception):
    """Raised by create_user() when the username is already taken."""


async def count_users() -> int:
    try:
        async with await _acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) AS n FROM app_user")
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Counting users failed: {e}") from e
    return row["n"]


async def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    try:
        async with await _acquire() as conn:
            row = await conn.fetchrow(
                "SELECT username, password_hash, role FROM app_user WHERE username = $1", username
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Fetching user failed: {e}") from e
    return dict(row) if row is not None else None


async def create_user(username: str, password_hash: str, role: str = "member") -> Dict[str, Any]:
    try:
        async with await _acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO app_user (username, password_hash, role) VALUES ($1, $2, $3)",
                    username,
                    password_hash,
                    role,
                )
            except asyncpg.UniqueViolationError as e:
                raise UsernameConflict(f"User '{username}' already exists") from e
    except (RepositoryUnavailable, UsernameConflict):
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Creating user failed: {e}") from e
    return {"username": username, "role": role}


async def list_users() -> List[Dict[str, Any]]:
    try:
        async with await _acquire() as conn:
            rows = await conn.fetch("SELECT username, role, created_at FROM app_user ORDER BY username")
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Listing users failed: {e}") from e
    return [
        {"username": r["username"], "role": r["role"], "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


async def update_user_password(username: str, password_hash: str) -> bool:
    try:
        async with await _acquire() as conn:
            result = await conn.execute(
                "UPDATE app_user SET password_hash = $1 WHERE username = $2", password_hash, username
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Updating password failed: {e}") from e
    return result != "UPDATE 0"


async def delete_user(username: str) -> bool:
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM app_user WHERE username = $1", username)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Deleting user failed: {e}") from e
    return result != "DELETE 0"


async def seed_instances_from_yaml(seed: List[InstanceConfig]) -> int:
    """Insert any seed entry whose name isn't already registered. Never
    overwrites an existing row — once an instance exists (from a prior seed,
    or created through the UI), this never touches it again. Called once at
    startup (see app/main.py's lifespan)."""
    if not seed:
        return 0
    inserted = 0
    try:
        async with await _acquire() as conn:
            for item in seed:
                encrypted = crypto.encrypt(item.mssql_connection_string)
                result = await conn.execute(
                    """
                    INSERT INTO instance (name, label, environment, connection_string_encrypted)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (name) DO NOTHING
                    """,
                    item.name,
                    item.label,
                    item.environment,
                    encrypted,
                )
                if result == "INSERT 0 1":
                    inserted += 1
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Seeding instances failed: {e}") from e
    return inserted
