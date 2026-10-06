"""Repository implementation."""

from typing import Any, List, Optional
import asyncpg
from app.core import crypto
from app.core.config import InstanceConfig
from app.infrastructure.postgres.pool import RepositoryUnavailable
from app.infrastructure.postgres.pool import _acquire
from app.infrastructure.postgres.pool import _invalidate_pool_on_failure


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
