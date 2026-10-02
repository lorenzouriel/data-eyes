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

import json
import logging
from contextlib import asynccontextmanager
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


async def insert_activity_sample(instance_name: str, rows: List[Dict[str, Any]]) -> None:
    """Bulk-append one row per currently-active session this cycle — see
    app/collector.py's _collect_activity_sample for how rows are built from
    diagnostics.active_sessions(). The single append-only log backing the
    Programs/Databases/Machines/DB Users/Plans/SQL Statements Top-10 history
    and the query drill-down for every other dimension."""
    if not rows:
        return
    captured_at = datetime.now(timezone.utc)
    values = [
        (
            captured_at,
            instance_name,
            r.get("session_id"),
            r.get("database_name"),
            r.get("program_name"),
            r.get("host_name"),
            r.get("login_name"),
            r.get("wait_type"),
            r.get("wait_category"),
            r.get("wait_time_ms") or 0.0,
            r.get("elapsed_time_ms") or 0.0,
            r.get("plan_handle"),
            r.get("query_hash"),
            r.get("sql_text"),
        )
        for r in rows
    ]
    try:
        async with await _acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO activity_sample
                    (captured_at, instance_name, session_id, database_name, program_name, host_name,
                     login_name, wait_type, wait_category, wait_time_ms, elapsed_time_ms, plan_handle,
                     query_hash, sql_text)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                """,
                values,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Activity-sample insert failed: {e}") from e


async def prune_old_activity_samples(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM activity_sample WHERE captured_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Activity-sample prune failed: {e}") from e
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def insert_file_io_snapshot(instance_name: str, deltas: List[Dict[str, Any]]) -> None:
    """Same delta-of-cumulative-counter pattern as insert_wait_category_snapshot
    — deltas is this cycle's per-file IO-stall/bytes/count delta, already
    computed by the caller (app/collector.py's _collect_file_io)."""
    if not deltas:
        return
    captured_at = datetime.now(timezone.utc)
    values = [
        (
            captured_at,
            instance_name,
            d["database_name"],
            d["file_name"],
            d.get("drive"),
            d["io_stall_ms"],
            d.get("io_bytes") or 0.0,
            d.get("io_count") or 0.0,
        )
        for d in deltas
    ]
    try:
        async with await _acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO file_io_snapshot
                    (captured_at, instance_name, database_name, file_name, drive, io_stall_ms, io_bytes, io_count)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                values,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"File-IO snapshot insert failed: {e}") from e


async def get_latest_drive_io(instance_name: str, within_seconds: int = 180) -> Dict[str, Dict[str, float]]:
    """Per-drive IO rate + average latency from the most recent file_io_snapshot
    cycle(s) within the window — reads the collector's own recent delta rows
    (Postgres) rather than issuing another live SQL Server query, so the
    fleet Cards' Disk & IO section doesn't add extra per-poll DMV cost on top
    of the health rollup. within_seconds should comfortably exceed one
    collector interval so a slightly-late cycle still shows a value."""
    since = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
    try:
        async with await _acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT drive,
                       SUM(io_bytes) AS total_bytes,
                       SUM(io_stall_ms) AS total_stall_ms,
                       SUM(io_count) AS total_count,
                       MIN(captured_at) AS earliest,
                       MAX(captured_at) AS latest
                FROM file_io_snapshot
                WHERE instance_name = $1 AND captured_at >= $2 AND drive IS NOT NULL
                GROUP BY drive
                """,
                instance_name,
                since,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Drive-IO query failed: {e}") from e

    result: Dict[str, Dict[str, float]] = {}
    for row in rows:
        # Each row is a delta covering the interval *before* its captured_at, so
        # N cycles from earliest..latest cover (latest - earliest) + one interval.
        span_seconds = max(
            (row["latest"] - row["earliest"]).total_seconds() + settings.COLLECTOR_INTERVAL_SECONDS, 1.0
        )
        count = row["total_count"] or 0.0
        result[row["drive"]] = {
            "io_bytes_per_sec": (row["total_bytes"] or 0.0) / span_seconds,
            "latency_ms": (row["total_stall_ms"] / count) if count else 0.0,
        }
    return result


async def insert_category_snapshot(instance_name: str, category: str, severity: str, metric_value: Optional[float]) -> None:
    """A single-category metric_snapshot row with a real, caller-computed
    severity — for signals like 'errors' that (unlike the 8 fleet_health_score
    categories) are only meaningful as a delta over time, so they're written
    by app/collector.py's periodic jobs rather than assembled inside
    diagnostics.fleet_health_score's own live-query rollup."""
    captured_at = datetime.now(timezone.utc)
    try:
        async with await _acquire() as conn:
            await conn.execute(
                """
                INSERT INTO metric_snapshot
                    (captured_at, instance_name, overall_severity, category, severity, metric_value)
                VALUES ($1, $2, $3, $4, $3, $5)
                """,
                captured_at,
                instance_name,
                severity,
                category,
                metric_value,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Category snapshot insert failed: {e}") from e


async def get_latest_category_severity(
    instance_name: str, category: str, max_age_seconds: Optional[int] = None
) -> Optional[str]:
    """Latest severity for a category. With max_age_seconds, a reading older
    than that is treated as unknown (None) so a stale CRITICAL can't persist
    after the collector stops writing (instance down, counter reset, etc.)."""
    if max_age_seconds is None:
        max_age_seconds = max(5 * settings.COLLECTOR_INTERVAL_SECONDS, 300)
    since = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    try:
        async with await _acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT severity FROM metric_snapshot
                WHERE instance_name = $1 AND category = $2 AND captured_at >= $3
                ORDER BY captured_at DESC LIMIT 1
                """,
                instance_name,
                category,
                since,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Category severity query failed: {e}") from e
    return row["severity"] if row is not None else None


async def prune_old_file_io_snapshots(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM file_io_snapshot WHERE captured_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"File-IO snapshot prune failed: {e}") from e
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def insert_deadlock_events(instance_name: str, events: List[Dict[str, Any]]) -> None:
    """Durable copy of whatever new (not-already-persisted) deadlock graphs
    app/collector.py's _collect_deadlocks found in the system_health ring
    buffer this cycle. ON CONFLICT DO NOTHING is a belt-and-suspenders dedup
    on top of the collector's own in-memory last-seen marker, in case that
    marker is lost to a backend restart mid-buffer."""
    if not events:
        return
    captured_at = datetime.now(timezone.utc)
    values = []
    for e in events:
        occurred_at_raw = e.get("occurred_at")
        if not occurred_at_raw:
            continue
        occurred_at = datetime.fromisoformat(occurred_at_raw.replace("Z", "+00:00"))
        values.append(
            (
                occurred_at,
                captured_at,
                instance_name,
                e.get("database_name"),
                e.get("victim_login"),
                e.get("victim_host"),
                e.get("victim_program"),
                e.get("resource_description"),
                e.get("process_count") or 0,
                e.get("summary"),
            )
        )
    if not values:
        return
    try:
        async with await _acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO deadlock_event
                    (occurred_at, captured_at, instance_name, database_name, victim_login,
                     victim_host, victim_program, resource_description, process_count, summary)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (instance_name, occurred_at) DO NOTHING
                """,
                values,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Deadlock-event insert failed: {e}") from e


async def prune_old_deadlock_events(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM deadlock_event WHERE occurred_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Deadlock-event prune failed: {e}") from e
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


# Whitelisted Top-N dimensions — get_top_dimension_history/get_dimension_log
# interpolate table/column names (never caller input directly) into raw SQL,
# so `dimension` MUST be validated against DIMENSION_NAMES by the router
# before either function is called. "deadlocks" isn't in this dict (it's a
# single-series count, no top-N grouping key) but is handled by both
# functions as a special case and IS included in DIMENSION_NAMES.
_DIMENSIONS: Dict[str, Dict[str, Any]] = {
    "waits":               {"table": "wait_category_snapshot", "key": "category",     "value": "seconds",         "ms": False},
    "programs":            {"table": "activity_sample",        "key": "program_name", "value": "wait_time_ms",    "ms": True},
    "databases":           {"table": "activity_sample",        "key": "database_name","value": "wait_time_ms",    "ms": True},
    "machines":            {"table": "activity_sample",        "key": "host_name",    "value": "wait_time_ms",    "ms": True},
    "db_users":            {"table": "activity_sample",        "key": "login_name",   "value": "wait_time_ms",    "ms": True},
    "plans":               {"table": "activity_sample",        "key": "plan_handle",  "value": "wait_time_ms",    "ms": True},
    "sql_statements":      {"table": "activity_sample",        "key": "query_hash",   "value": "wait_time_ms",    "ms": True},
    "files":               {"table": "file_io_snapshot",       "key": "file_name",    "value": "io_stall_ms",     "ms": True},
    "drives":              {"table": "file_io_snapshot",       "key": "drive",        "value": "io_stall_ms",     "ms": True},
    "blocking_statements": {"table": "blocking_event",         "key": "root_sql",     "value": "duration_seconds","ms": False},
}

DIMENSION_NAMES = frozenset(_DIMENSIONS) | {"deadlocks"}

# Where to pull a friendlier display label from, for dimensions whose raw key
# isn't human-readable on its own (a plan_handle hex string, a query_hash).
_LABEL_LOOKUP = {
    "plans": ("activity_sample", "plan_handle", "sql_text"),
    "sql_statements": ("activity_sample", "query_hash", "sql_text"),
}


async def get_top_dimension_history(instance_name: str, dimension: str, since_days: int, limit: int = 10) -> Dict[str, Any]:
    """Day-bucketed Top-N series (+ an 'Other' rollup for everything outside
    the top N keys) for one of the whitelisted dimensions above."""
    since = datetime.now(timezone.utc) - timedelta(days=since_days)

    try:
        async with await _acquire() as conn:
            if dimension == "deadlocks":
                rows = await conn.fetch(
                    """
                    SELECT date_trunc('day', occurred_at) AS day, COUNT(*) AS value
                    FROM deadlock_event
                    WHERE instance_name = $1 AND occurred_at >= $2
                    GROUP BY day ORDER BY day ASC
                    """,
                    instance_name,
                    since,
                )
                points = [{"day": r["day"].date().isoformat(), "value": r["value"]} for r in rows]
                return {"series": [{"key": "deadlocks", "label": "Deadlocks", "points": points}], "other": []}

            spec = _DIMENSIONS[dimension]
            table, key_col, value_col = spec["table"], spec["key"], spec["value"]
            value_expr = f"{value_col} / 1000.0" if spec["ms"] else value_col

            top_rows = await conn.fetch(
                f"""
                SELECT {key_col} AS key, SUM({value_expr}) AS total
                FROM {table}
                WHERE instance_name = $1 AND captured_at >= $2 AND {key_col} IS NOT NULL
                GROUP BY {key_col}
                ORDER BY total DESC
                LIMIT $3
                """,
                instance_name,
                since,
                limit,
            )
            top_keys = [r["key"] for r in top_rows]

            labels: Dict[str, str] = {k: k for k in top_keys}
            if dimension in _LABEL_LOOKUP and top_keys:
                label_table, label_key_col, label_col = _LABEL_LOOKUP[dimension]
                label_rows = await conn.fetch(
                    f"""
                    SELECT DISTINCT ON ({label_key_col}) {label_key_col} AS key, {label_col} AS label
                    FROM {label_table}
                    WHERE instance_name = $1 AND {label_key_col} = ANY($2::text[])
                    ORDER BY {label_key_col}, captured_at DESC
                    """,
                    instance_name,
                    top_keys,
                )
                for r in label_rows:
                    if r["label"]:
                        labels[r["key"]] = r["label"][:120]

            day_rows = await conn.fetch(
                f"""
                SELECT
                    date_trunc('day', captured_at) AS day,
                    CASE WHEN {key_col} = ANY($3::text[]) THEN {key_col} ELSE NULL END AS bucket_key,
                    SUM({value_expr}) AS value
                FROM {table}
                WHERE instance_name = $1 AND captured_at >= $2
                GROUP BY day, bucket_key
                ORDER BY day ASC
                """,
                instance_name,
                since,
                top_keys,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Dimension history query failed ({dimension}): {e}") from e

    series_points: Dict[str, List[Dict[str, Any]]] = {k: [] for k in top_keys}
    other_points: List[Dict[str, Any]] = []
    for row in day_rows:
        day_iso = row["day"].date().isoformat()
        if row["bucket_key"] is None:
            other_points.append({"day": day_iso, "value": row["value"]})
        else:
            series_points[row["bucket_key"]].append({"day": day_iso, "value": row["value"]})

    series = [{"key": key, "label": labels.get(key, key), "points": series_points[key]} for key in top_keys]
    return {"series": series, "other": other_points}


_ACTIVITY_LOG_COLUMNS = (
    "captured_at, database_name, program_name, host_name, login_name, wait_type, "
    "wait_category, wait_time_ms, elapsed_time_ms, plan_handle, sql_text"
)
_ACTIVITY_DIMENSIONS = {"waits", "programs", "databases", "machines", "db_users", "plans", "sql_statements"}


async def get_dimension_log(instance_name: str, dimension: str, day: str) -> List[Dict[str, Any]]:
    """Raw rows for the Specific-Day drill-down — reads whichever table
    get_top_dimension_history reads from for that dimension, filtered to one
    calendar day, no aggregation. For dimension='waits' specifically, this
    reads activity_sample (not wait_category_snapshot, which carries no query
    text) — the direct answer to 'wait_type is high, show me the queries'."""
    day_start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    if dimension in _ACTIVITY_DIMENSIONS:
        table, time_col, columns = "activity_sample", "captured_at", _ACTIVITY_LOG_COLUMNS
    elif dimension in ("files", "drives"):
        table, time_col, columns = "file_io_snapshot", "captured_at", "captured_at, database_name, file_name, drive, io_stall_ms"
    elif dimension == "blocking_statements":
        table, time_col, columns = "blocking_event", "captured_at", "captured_at, root_sql, lock_type, blocked_count, duration_seconds"
    elif dimension == "deadlocks":
        table, time_col, columns = (
            "deadlock_event",
            "occurred_at",
            "occurred_at, database_name, victim_login, victim_host, victim_program, resource_description, process_count, summary",
        )
    else:
        raise ValueError(f"Unknown dimension: {dimension}")

    try:
        async with await _acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {columns}
                FROM {table}
                WHERE instance_name = $1 AND {time_col} >= $2 AND {time_col} < $3
                ORDER BY {time_col} DESC
                LIMIT 500
                """,
                instance_name,
                day_start,
                day_end,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Dimension log query failed ({dimension}): {e}") from e

    result = []
    for row in rows:
        item = dict(row)
        for key in ("captured_at", "occurred_at"):
            if item.get(key) is not None:
                item[key] = item[key].isoformat()
        result.append(item)
    return result


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


async def update_user_password(username: str, password_hash: str, expected_hash: str) -> bool:
    try:
        async with await _acquire() as conn:
            async with conn.transaction():
                result = await conn.execute(
                    "UPDATE app_user SET password_hash = $1 WHERE username = $2 AND password_hash = $3",
                    password_hash, username, expected_hash,
                )
                if result == "UPDATE 0":
                    return False
                await conn.execute("DELETE FROM app_session WHERE username = $1", username)
        return True
    except Exception as e:
        raise RepositoryUnavailable("Password update unavailable") from e


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
    """Synchronize shared-YAML entries into the dashboard registry.

    YAML owns entries with matching names. UI-only entries absent from YAML
    are preserved.
    """
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
                    ON CONFLICT (name) DO UPDATE SET
                        label = EXCLUDED.label,
                        environment = EXCLUDED.environment,
                        connection_string_encrypted = EXCLUDED.connection_string_encrypted,
                        updated_at = now()
                    """,
                    item.name,
                    item.label,
                    item.environment,
                    encrypted,
                )
                if result in ("INSERT 0 1", "UPDATE 1"):
                    inserted += 1
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Seeding instances failed: {e}") from e
    return inserted


async def ensure_security_schema():
    from pathlib import Path
    async with await _acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(20260926)")
            await conn.execute(Path(__file__).with_name("security_schema.sql").read_text())


async def create_session(token_hash: str, username: str, password_hash: str, lifetime: int) -> bool:
    try:
        async with await _acquire() as conn:
            async with conn.transaction():
                # Serialize with password changes/deletion so a concurrent login
                # cannot resurrect a session after credentials are revoked.
                row = await conn.fetchrow("SELECT password_hash FROM app_user WHERE username=$1 FOR UPDATE", username)
                if row is None or row["password_hash"] != password_hash:
                    return False
                await conn.execute("DELETE FROM app_session WHERE expires_at <= now()")
                await conn.execute(
                    "INSERT INTO app_session VALUES ($1, $2, now() + $3 * interval '1 second')",
                    token_hash, username, lifetime,
                )
        return True
    except Exception as e:
        raise RepositoryUnavailable("Session creation unavailable") from e


async def get_session_user(token_hash: str):
    try:
        async with await _acquire() as conn:
            row = await conn.fetchrow(
                "SELECT u.username, u.role, u.password_hash FROM app_session s "
                "JOIN app_user u ON u.username=s.username "
                "WHERE s.token_hash=$1 AND s.expires_at > now()", token_hash,
            )
        return dict(row) if row else None
    except Exception as e:
        raise RepositoryUnavailable("Session validation unavailable") from e


async def revoke_session(token_hash: str):
    try:
        async with await _acquire() as conn:
            await conn.execute("DELETE FROM app_session WHERE token_hash=$1", token_hash)
    except Exception as e:
        raise RepositoryUnavailable("Session revocation unavailable") from e


async def consume_quota(bucket: str, limit: int, seconds: int) -> bool:
    try:
        async with await _acquire() as conn:
            await conn.execute("DELETE FROM security_rate_limit WHERE expires_at <= now()")
            row = await conn.fetchrow(
                "INSERT INTO security_rate_limit VALUES ($1, 1, now() + $2 * interval '1 second') "
                "ON CONFLICT (bucket) DO UPDATE SET attempts = security_rate_limit.attempts + 1 "
                "WHERE security_rate_limit.attempts < $3 RETURNING attempts", bucket, seconds, limit,
            )
        return row is not None
    except Exception as e:
        raise RepositoryUnavailable("Rate limit service unavailable") from e


@asynccontextmanager
async def notification_connection():
    """Normalize DB failures without leaking encrypted channel configuration."""
    try:
        async with await _acquire() as conn:
            yield conn
    except (asyncpg.PostgresError, OSError, RepositoryUnavailable) as exc:
        raise RepositoryUnavailable("Notification repository unavailable") from exc


async def ensure_notification_schema():
    from pathlib import Path
    async with notification_connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(20261002)")
            await conn.execute(Path(__file__).with_name("notification_schema.sql").read_text(encoding="utf-8"))


def _notification_channel(row, decrypt=False):
    if row is None:
        return None
    from .notifications.models import SECRET_FIELDS, MASK
    result = dict(row)
    config = json.loads(crypto.decrypt(result["config"]))
    result["config"] = config if decrypt else {
        key: MASK if key in SECRET_FIELDS and value else value for key, value in config.items()
    }
    return result


async def list_notification_channels():
    async with notification_connection() as conn:
        rows = await conn.fetch("SELECT * FROM notification_channel ORDER BY id")
    return [_notification_channel(row) for row in rows]


async def get_notification_channel(channel_id, *, decrypt=False):
    async with notification_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM notification_channel WHERE id=$1", channel_id)
    return _notification_channel(row, decrypt)


async def save_notification_channel(payload, channel_id=None):
    encrypted = crypto.encrypt(json.dumps(payload["config"]))
    async with notification_connection() as conn:
        if channel_id is None:
            row = await conn.fetchrow(
                "INSERT INTO notification_channel(name,type,enabled,config) VALUES($1,$2,$3,$4) RETURNING *",
                payload["name"], payload["type"], payload["enabled"], encrypted)
        else:
            row = await conn.fetchrow(
                "UPDATE notification_channel SET name=$1,type=$2,enabled=$3,config=$4 WHERE id=$5 RETURNING *",
                payload["name"], payload["type"], payload["enabled"], encrypted, channel_id)
    return _notification_channel(row)


def _notification_rule(row):
    if row is None:
        return None
    result = dict(row)
    return {**json.loads(result.pop("definition")), **result}


async def list_notification_rules():
    async with notification_connection() as conn:
        rows = await conn.fetch("SELECT * FROM notification_rule ORDER BY id")
    return [_notification_rule(row) for row in rows]


async def save_notification_rule(payload, rule_id=None):
    async with notification_connection() as conn:
        if rule_id is None:
            row = await conn.fetchrow(
                "INSERT INTO notification_rule(channel_id,name,enabled,definition) VALUES($1,$2,$3,$4::jsonb) RETURNING *",
                payload["channel_id"], payload["name"], payload["enabled"], json.dumps(payload))
        else:
            row = await conn.fetchrow(
                "UPDATE notification_rule SET channel_id=$1,name=$2,enabled=$3,definition=$4::jsonb WHERE id=$5 RETURNING *",
                payload["channel_id"], payload["name"], payload["enabled"], json.dumps(payload), rule_id)
    return _notification_rule(row)


async def delete_notification(kind, row_id):
    table = {"channels": "notification_channel", "rules": "notification_rule", "logs": "notification_log"}[kind]
    async with notification_connection() as conn:
        # Delivery records are immutable while queued or in flight.
        suffix = " AND status NOT IN ('pending','sending')" if kind == "logs" else ""
        result = await conn.execute(f"DELETE FROM {table} WHERE id=$1{suffix}", row_id)
    return result == "DELETE 1"


async def list_notification_logs(limit=100, offset=0, channel_id=None):
    async with notification_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM notification_log WHERE ($3::bigint IS NULL OR channel_id=$3) "
            "ORDER BY id DESC LIMIT $1 OFFSET $2", limit, offset, channel_id)
    return [{**dict(row), "event": json.loads(row["event"])} for row in rows]


async def enqueue_notifications(planner, since):
    """Atomically persist transitions and their outbox records across workers."""
    now = datetime.now(timezone.utc)
    async with notification_connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(20261003)")
            snapshots = await conn.fetch(
                "SELECT DISTINCT ON (instance_name, category) instance_name, category, severity, metric_value, captured_at "
                "FROM metric_snapshot WHERE captured_at >= $1 ORDER BY instance_name, category, captured_at DESC", since)
            states = await conn.fetch("SELECT * FROM notification_state")
            rules = await conn.fetch(
                "SELECT r.* FROM notification_rule r JOIN notification_channel c ON c.id=r.channel_id "
                "WHERE r.enabled AND c.enabled")
            previous = await conn.fetch(
                "SELECT rule_id,instance_name,category,max(created_at) AS last_sent FROM notification_log "
                "WHERE status != 'suppressed' AND created_at >= $1 GROUP BY rule_id,instance_name,category",
                now - timedelta(days=7))
            planned = planner(snapshots, states, [_notification_rule(r) for r in rules], previous, now)
            for snapshot in snapshots:
                await conn.execute(
                    "INSERT INTO notification_state VALUES($1,$2,$3,$4) ON CONFLICT(instance_name,category) "
                    "DO UPDATE SET severity=excluded.severity,captured_at=excluded.captured_at "
                    "WHERE notification_state.captured_at < excluded.captured_at",
                    snapshot["instance_name"], snapshot["category"], snapshot["severity"], snapshot["captured_at"])
            for rule, event, reason in planned:
                await conn.execute(
                    "INSERT INTO notification_log(channel_id,rule_id,instance_name,category,event,status,message,created_at) "
                    "VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,$8)", rule["channel_id"], rule["id"], event.instance,
                    event.category, event.model_dump_json(), "suppressed" if reason else "pending", reason, now)


async def claim_notification():
    async with notification_connection() as conn:
        row = await conn.fetchrow(
            "UPDATE notification_log SET status='sending', attempts=attempts+1, "
            "next_attempt_at=now()+interval '5 minutes' WHERE id=("
            "SELECT id FROM notification_log WHERE status IN ('pending','sending') AND next_attempt_at<=now() "
            "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *")
    return dict(row) if row else None


async def finish_notification(row, result):
    retry = result.retryable and row["attempts"] < 3
    async with notification_connection() as conn:
        await conn.execute(
            "UPDATE notification_log SET status=$2,message=$3,next_attempt_at=$4,delivered_at=$5 "
            "WHERE id=$1 AND status='sending' AND attempts=$6",
            row["id"], "sent" if result.ok else "pending" if retry else "failed", result.message,
            datetime.now(timezone.utc) + timedelta(seconds=max(30, result.retry_after)),
            datetime.now(timezone.utc) if result.ok else None, row["attempts"])


async def log_notification_test(channel_id, event, result):
    async with notification_connection() as conn:
        await conn.execute(
            "INSERT INTO notification_log(channel_id,instance_name,category,event,status,message,attempts,delivered_at) "
            "VALUES($1,$2,$3,$4::jsonb,$5,$6,$7,$8)", channel_id, event.instance, event.category,
            event.model_dump_json(), "sent" if result.ok else "failed", result.message, result.attempts,
            datetime.now(timezone.utc) if result.ok else None)
