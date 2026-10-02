"""
Instance registry API.

- GET  /api/instances                — list registered instances (connection
                                        string never returned, see InstanceSummary)
- POST /api/instances                — register a new instance
- PUT  /api/instances/{name}         — partial update
- DELETE /api/instances/{name}       — remove an instance
- GET  /api/instances/{name}         — single-instance detail + database list
                                        (the database picker between the Main
                                        Page and a per-database drill-down)

Only administrators can manage or test instances — one shared team, not per-user
ownership (see app/auth.py's docstring for the tenancy model this assumes).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from .. import diagnostics, repository
from ..auth import require_auth, require_admin
from ..connection_policy import validate_connection_string
from ..config import InstanceConfig
from ..mssql_client import MSSQLError

router = APIRouter(prefix="/api/instances", tags=["instances"])


class InstanceSummary(BaseModel):
    """Instance shape returned to the frontend — never includes the
    connection string, encrypted or otherwise."""

    name: str
    label: str
    environment: Optional[str] = None

    @classmethod
    def from_config(cls, instance: InstanceConfig) -> "InstanceSummary":
        return cls(name=instance.name, label=instance.label, environment=instance.environment)


class InstanceCreateRequest(BaseModel):
    name: str
    label: str
    environment: Optional[str] = None
    connection_string: str = Field(max_length=4096)

    _validate_connection = field_validator("connection_string")(validate_connection_string)


class InstanceUpdateRequest(BaseModel):
    label: Optional[str] = None
    environment: Optional[str] = None
    clear_environment: bool = False
    connection_string: Optional[str] = Field(default=None, max_length=4096)

    @field_validator("connection_string")
    @classmethod
    def validate_connection(cls, value):
        return validate_connection_string(value) if value is not None else None


class TestConnectionRequest(InstanceUpdateRequest):
    connection_string: Optional[str] = Field(default=None, max_length=4096)

class TestConnectionResult(BaseModel):
    ok: bool
    message: str


async def _find_instance(instance_name: str) -> InstanceConfig:
    try:
        instance = await repository.get_instance(instance_name)
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Instance registry unavailable: {e}") from e
    if not instance:
        raise HTTPException(status_code=404, detail=f"Unknown instance: {instance_name}")
    return instance


@router.get("", response_model=list[InstanceSummary])
async def list_instances(_: str = Depends(require_auth)):
    try:
        instances = await repository.list_instances()
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Instance registry unavailable: {e}") from e
    return [InstanceSummary.from_config(i) for i in instances]


@router.post("", response_model=InstanceSummary, status_code=201)
async def create_instance(payload: InstanceCreateRequest, username: str = Depends(require_admin)):
    try:
        instance = await repository.create_instance(
            name=payload.name,
            label=payload.label,
            environment=payload.environment,
            connection_string=payload.connection_string,
            created_by=username,
        )
    except repository.InstanceNameConflict as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Instance registry unavailable: {e}") from e
    return InstanceSummary.from_config(instance)


@router.post("/test-connection", response_model=TestConnectionResult)
async def test_connection(payload: TestConnectionRequest, _: str = Depends(require_admin)):
    """Try a connection string before it's saved — used by the Add/Edit
    instance form's "Test connection" button."""
    if not payload.connection_string:
        raise HTTPException(status_code=400, detail="connection_string is required")
    try:
        databases = await diagnostics.list_databases(payload.connection_string)
    except MSSQLError as e:
        return TestConnectionResult(ok=False, message=str(e))
    count = len(databases) if isinstance(databases, list) else 0
    return TestConnectionResult(ok=True, message=f"Connected — found {count} database{'s' if count != 1 else ''}")


@router.post("/{instance_name}/test-connection", response_model=TestConnectionResult)
async def test_instance_connection(
    instance_name: str, payload: TestConnectionRequest, _: str = Depends(require_admin)
):
    """Same as /test-connection, but for the Edit form: when the connection
    string field is left blank (keep the current one), fall back to the
    already-registered string instead of requiring it to be retyped."""
    connection_string = payload.connection_string
    if not connection_string:
        instance = await _find_instance(instance_name)
        connection_string = instance.mssql_connection_string
    try:
        databases = await diagnostics.list_databases(connection_string)
    except MSSQLError as e:
        return TestConnectionResult(ok=False, message=str(e))
    count = len(databases) if isinstance(databases, list) else 0
    return TestConnectionResult(ok=True, message=f"Connected — found {count} database{'s' if count != 1 else ''}")


@router.put("/{instance_name}", response_model=InstanceSummary)
async def update_instance(
    instance_name: str, payload: InstanceUpdateRequest, _: str = Depends(require_admin)
):
    try:
        instance = await repository.update_instance(
            instance_name,
            label=payload.label,
            environment=payload.environment,
            connection_string=payload.connection_string,
            clear_environment=payload.clear_environment,
        )
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Instance registry unavailable: {e}") from e
    if not instance:
        raise HTTPException(status_code=404, detail=f"Unknown instance: {instance_name}")
    return InstanceSummary.from_config(instance)


@router.delete("/{instance_name}", status_code=204)
async def delete_instance(instance_name: str, _: str = Depends(require_admin)):
    try:
        deleted = await repository.delete_instance(instance_name)
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Instance registry unavailable: {e}") from e
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Unknown instance: {instance_name}")


@router.get("/{instance_name}")
async def get_instance(instance_name: str, _: str = Depends(require_auth)):
    instance = await _find_instance(instance_name)
    try:
        databases = await diagnostics.list_databases(instance.mssql_connection_string)
    except MSSQLError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return {
        "name": instance.name,
        "label": instance.label,
        "environment": instance.environment,
        "databases": databases if isinstance(databases, list) else [],
    }
