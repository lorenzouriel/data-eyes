"""Repository implementation."""

from app.infrastructure.postgres.pool import RepositoryUnavailable
from app.infrastructure.postgres.pool import _acquire


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
