"""Repository implementation."""

from typing import Any, Dict, List, Optional
import asyncpg
from app.infrastructure.postgres.pool import RepositoryUnavailable
from app.infrastructure.postgres.pool import _acquire
from app.infrastructure.postgres.pool import _invalidate_pool_on_failure


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
