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

from .config import settings

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
