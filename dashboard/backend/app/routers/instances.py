"""Instance-level API — the database picker between the Main Page and a
per-database tabbed drill-down (GET /instances/:id in the rearchitecture
plan's routing table)."""

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_auth
from ..config import InstanceConfig, load_instances, settings
from ..mcp_client import MCPToolError, call_tool

router = APIRouter(prefix="/api/instances", tags=["instances"])


def _find_instance(instance_name: str) -> InstanceConfig:
    instances = {i.name: i for i in load_instances()}
    instance = instances.get(instance_name)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Unknown instance: {instance_name}")
    return instance


@router.get("/{instance_name}")
async def get_instance(instance_name: str, _: str = Depends(require_auth)):
    instance = _find_instance(instance_name)
    try:
        databases = await call_tool(
            instance.mcp_url, "list_databases", {}, timeout=settings.MCP_CALL_TIMEOUT_SECONDS
        )
    except MCPToolError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return {
        "name": instance.name,
        "label": instance.label,
        "environment": instance.environment,
        "databases": databases if isinstance(databases, list) else [],
    }
