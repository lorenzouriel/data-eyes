"""
Per-database DPA-style tabbed drill-down API.

Each tab maps to one or more MCP diagnostic tools — see
.claude/knowledge-base/_static/taxonomy.md for the authoritative
category-to-tool mapping this mirrors. Every sub-call is independently
error-handled (see _safe_call): a failing tool degrades only that one
section of a tab, it never fails the whole tab, matching the same
graceful-degradation shape as health_score.py's per-instance handling.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_auth
from ..config import InstanceConfig, load_instances, settings
from ..mcp_client import MCPToolError, call_tool

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/instances/{instance_name}/databases/{database_name}", tags=["databases"]
)


def _find_instance(instance_name: str) -> InstanceConfig:
    instances = {i.name: i for i in load_instances()}
    instance = instances.get(instance_name)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Unknown instance: {instance_name}")
    return instance


async def _safe_call(mcp_url: str, tool: str, arguments: dict) -> Dict[str, Any]:
    try:
        result = await call_tool(mcp_url, tool, arguments, timeout=settings.MCP_CALL_TIMEOUT_SECONDS)
        return {"data": result, "error": None}
    except MCPToolError as e:
        logger.warning("Tab tool call failed: tool=%s error=%s", tool, e)
        return {"data": None, "error": str(e)}


async def _gather_named(mcp_url: str, calls: Dict[str, Tuple[str, dict]]) -> Dict[str, Any]:
    """calls: {result_key: (tool_name, arguments)} -> {result_key: {data, error}}"""
    keys = list(calls.keys())
    coros = [_safe_call(mcp_url, calls[k][0], calls[k][1]) for k in keys]
    results = await asyncio.gather(*coros)
    return dict(zip(keys, results))


def _filter_rows_by_database(data: Any, db: str, key: str = "DatabaseName") -> Any:
    """blocking_snapshot and ag_health are instance-wide tools; narrow their
    rows to the database this tab is scoped to."""
    if not isinstance(data, list):
        return data
    return [row for row in data if isinstance(row, dict) and str(row.get(key, "")).lower() == db.lower()]


TabBuilder = Callable[[str, str], Awaitable[Dict[str, Any]]]
TAB_BUILDERS: Dict[str, TabBuilder] = {}


def tab(name: str):
    def decorator(fn: TabBuilder) -> TabBuilder:
        TAB_BUILDERS[name] = fn
        return fn

    return decorator


@tab("wait-time")
async def _wait_time(mcp_url: str, db: str) -> Dict[str, Any]:
    return await _gather_named(mcp_url, {"wait_stats": ("wait_stats", {"database": db})})


@tab("top-sql")
async def _top_sql(mcp_url: str, db: str) -> Dict[str, Any]:
    return await _gather_named(
        mcp_url,
        {
            "top_queries": ("top_queries", {"database": db}),
            "missing_indexes": ("missing_indexes", {"database": db}),
        },
    )


@tab("storage")
async def _storage(mcp_url: str, db: str) -> Dict[str, Any]:
    return await _gather_named(mcp_url, {"db_space": ("db_space", {"database": db})})


@tab("sessions-blocking")
async def _sessions_blocking(mcp_url: str, db: str) -> Dict[str, Any]:
    result = await _gather_named(mcp_url, {"blocking": ("blocking_snapshot", {})})
    result["blocking"]["data"] = _filter_rows_by_database(result["blocking"]["data"], db)
    return result


@tab("config-alerts")
async def _config_alerts(mcp_url: str, db: str) -> Dict[str, Any]:
    return await _gather_named(
        mcp_url,
        {
            "backup_health": ("backup_health", {"database": db}),
            "checkdb_health": ("checkdb_health", {"database": db}),
            "job_health": ("job_health", {}),
        },
    )


@tab("index-buffer")
async def _index_buffer(mcp_url: str, db: str) -> Dict[str, Any]:
    return await _gather_named(
        mcp_url,
        {
            "index_fragmentation": ("index_fragmentation", {"database": db}),
            "unused_indexes": ("unused_indexes", {"database": db}),
            "stale_statistics": ("stale_statistics", {"database": db}),
        },
    )


@tab("ag")
async def _ag(mcp_url: str, db: str) -> Dict[str, Any]:
    result = await _gather_named(mcp_url, {"ag_health": ("ag_health", {})})
    result["ag_health"]["data"] = _filter_rows_by_database(result["ag_health"]["data"], db)
    return result


@router.get("/tabs/{tab_name}")
async def get_tab(
    instance_name: str,
    database_name: str,
    tab_name: str,
    _: str = Depends(require_auth),
):
    builder = TAB_BUILDERS.get(tab_name)
    if not builder:
        raise HTTPException(
            status_code=404, detail=f"Unknown tab: {tab_name}. Valid: {sorted(TAB_BUILDERS)}"
        )
    instance = _find_instance(instance_name)
    return await builder(instance.mcp_url, database_name)
