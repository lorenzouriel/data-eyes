"""
Per-instance tabbed drill-down API — the Strata-design IA pivot from the
previous per-*database* drill-down (routers/databases.py) to per-*instance*.
Serves the Databases and Resources tabs; a `database` query param narrows
Resources where that's meaningful. Waits/Blocking/Sessions/SQL statements
moved to routers/activity.py's Top-N history (and live drill-down) instead
of a live-snapshot tab here.

Same TAB_BUILDERS / _safe_call / _gather_named pattern as
routers/databases.py: every sub-call is independently error-handled, a
failing query degrades only its own section, never the whole tab.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import diagnostics, repository
from ..auth import require_auth
from ..config import InstanceConfig
from ..mssql_client import MSSQLError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instances/{instance_name}", tags=["instance-tabs"])


async def _find_instance(instance_name: str) -> InstanceConfig:
    try:
        instance = await repository.get_instance(instance_name)
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Instance registry unavailable: {e}") from e
    if not instance:
        raise HTTPException(status_code=404, detail=f"Unknown instance: {instance_name}")
    return instance


async def _safe_call(coro: Awaitable[Any]) -> Dict[str, Any]:
    try:
        result = await coro
        return {"data": result, "error": None}
    except MSSQLError as e:
        logger.warning("Instance tab query failed: %s", e)
        return {"data": None, "error": str(e)}
    except repository.RepositoryUnavailable as e:
        logger.warning("Instance tab history query failed: %s", e)
        return {"data": None, "error": str(e)}


async def _gather_named(calls: Dict[str, Awaitable[Any]]) -> Dict[str, Any]:
    keys = list(calls.keys())
    results = await asyncio.gather(*(_safe_call(calls[k]) for k in keys))
    return dict(zip(keys, results))


# (connection_string, instance_name, database) -> {section: {data, error}}.
TabBuilder = Callable[[str, str, Optional[str]], Awaitable[Dict[str, Any]]]
TAB_BUILDERS: Dict[str, TabBuilder] = {}


def tab(name: str):
    def decorator(fn: TabBuilder) -> TabBuilder:
        TAB_BUILDERS[name] = fn
        return fn

    return decorator


@tab("databases")
async def _databases(conn_str: str, instance_name: str, database: Optional[str]) -> Dict[str, Any]:
    return await _gather_named({"databases": diagnostics.database_status(conn_str)})


@tab("resources")
async def _resources(conn_str: str, instance_name: str, database: Optional[str]) -> Dict[str, Any]:
    return await _gather_named(
        {
            "resources": diagnostics.resource_utilization(conn_str),
            "ag_health": diagnostics.ag_health(conn_str),
        }
    )


@router.get("/tabs/{tab_name}")
async def get_instance_tab(
    instance_name: str,
    tab_name: str,
    database: Optional[str] = Query(default=None),
    _: str = Depends(require_auth),
):
    builder = TAB_BUILDERS.get(tab_name)
    if not builder:
        raise HTTPException(status_code=404, detail=f"Unknown tab: {tab_name}. Valid: {sorted(TAB_BUILDERS)}")
    instance = await _find_instance(instance_name)
    return await builder(instance.mssql_connection_string, instance_name, database)


@router.get("/overview")
async def get_instance_overview(instance_name: str, _: str = Depends(require_auth)):
    """Header stats + row-expand detail: server facts + the current
    fleet_health_score rollup for this one instance."""
    instance = await _find_instance(instance_name)
    result = await _gather_named(
        {
            "server": diagnostics.server_overview(instance.mssql_connection_string),
            "health": diagnostics.fleet_health_score(instance.mssql_connection_string),
        }
    )
    return result
