"""Repository implementation."""

from app.infrastructure.postgres.pool import RepositoryUnavailable
from app.infrastructure.postgres.pool import _acquire
from app.infrastructure.postgres.pool import _invalidate_pool_on_failure


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
