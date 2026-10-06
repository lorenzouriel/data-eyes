"""Pool implementation."""

import logging
from typing import Optional
import asyncpg
from app.core.config import settings


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
