"""
Per-instance tabbed drill-down API — the Strata-design IA pivot from the
previous per-*database* drill-down (routers/databases.py) to per-*instance*.
Most diagnostics are already instance-wide (blocking, sessions, resources) or
optionally database-scoped (wait stats, top queries) — this router serves
the instance-first view; a `database` query param narrows individual
sections where that's meaningful, it's no longer the top-level unit.

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
# instance_name is unused by most builders (only waits/blocking need it, for
# the repository-backed history) but every builder takes it for a single
# consistent call signature.
TabBuilder = Callable[[str, str, Optional[str]], Awaitable[Dict[str, Any]]]
TAB_BUILDERS: Dict[str, TabBuilder] = {}


def tab(name: str):
    def decorator(fn: TabBuilder) -> TabBuilder:
        TAB_BUILDERS[name] = fn
        return fn

    return decorator


@tab("waits")
async def _waits(conn_str: str, instance_name: str, database: Optional[str]) -> Dict[str, Any]:
    return await _gather_named(
        {
            "wait_stats": diagnostics.wait_stats(conn_str, database=database),
            "wait_category_history": repository.get_wait_category_history(instance_name),
        }
    )


@tab("blocking")
async def _blocking(conn_str: str, instance_name: str, database: Optional[str]) -> Dict[str, Any]:
    return await _gather_named(
        {
            "blocking": diagnostics.blocking_snapshot(conn_str),
            "blocking_events": repository.get_blocking_events(instance_name),
        }
    )


@tab("sessions")
async def _sessions(conn_str: str, instance_name: str, database: Optional[str]) -> Dict[str, Any]:
    return await _gather_named(
        {
            "active_sessions": diagnostics.active_sessions(conn_str),
            "dimensions": diagnostics.session_dimensions(conn_str),
        }
    )


@tab("sql")
async def _sql(conn_str: str, instance_name: str, database: Optional[str]) -> Dict[str, Any]:
    return await _gather_named({"top_queries": diagnostics.top_queries(conn_str, database=database)})


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


@router.get("/plan")
async def get_query_plan(instance_name: str, plan_handle: str = Query(...), _: str = Depends(require_auth)):
    instance = await _find_instance(instance_name)
    try:
        return await diagnostics.query_plan(instance.mssql_connection_string, plan_handle)
    except MSSQLError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
