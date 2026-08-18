"""
Per-database DPA-style tabbed drill-down API.

Each tab maps to one or more app/diagnostics.py functions — see
.claude/knowledge-base/_static/taxonomy.md for the authoritative
category-to-query mapping this mirrors. Every sub-call is independently
error-handled (see _safe_call): a failing query degrades only that one
section of a tab, it never fails the whole tab, matching the same
graceful-degradation shape as health_score.py's per-instance handling.

Talks to SQL Server directly via app/diagnostics.py — no MCP hop. MCP is
reserved for agent use (Claude Code's sql-server-dba agent); this backend
just runs the same queries itself.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException

from .. import diagnostics, repository
from ..auth import require_auth
from ..config import InstanceConfig
from ..mssql_client import MSSQLError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/instances/{instance_name}/databases/{database_name}", tags=["databases"]
)


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
        logger.warning("Tab query failed: %s", e)
        return {"data": None, "error": str(e)}


async def _gather_named(calls: Dict[str, Awaitable[Any]]) -> Dict[str, Any]:
    """calls: {result_key: awaitable} -> {result_key: {data, error}}"""
    keys = list(calls.keys())
    results = await asyncio.gather(*(_safe_call(calls[k]) for k in keys))
    return dict(zip(keys, results))


def _filter_rows_by_database(data: Any, db: str, key: str = "DatabaseName") -> Any:
    """blocking_snapshot and ag_health are instance-wide queries; narrow their
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
async def _wait_time(conn_str: str, db: str) -> Dict[str, Any]:
    return await _gather_named({"wait_stats": diagnostics.wait_stats(conn_str, database=db)})


@tab("top-sql")
async def _top_sql(conn_str: str, db: str) -> Dict[str, Any]:
    return await _gather_named(
        {
            "top_queries": diagnostics.top_queries(conn_str, database=db),
            "missing_indexes": diagnostics.missing_indexes(conn_str, database=db),
        }
    )


@tab("storage")
async def _storage(conn_str: str, db: str) -> Dict[str, Any]:
    return await _gather_named({"db_space": diagnostics.db_space(conn_str, database=db)})


@tab("sessions-blocking")
async def _sessions_blocking(conn_str: str, db: str) -> Dict[str, Any]:
    result = await _gather_named({"blocking": diagnostics.blocking_snapshot(conn_str)})
    result["blocking"]["data"] = _filter_rows_by_database(result["blocking"]["data"], db)
    return result


@tab("config-alerts")
async def _config_alerts(conn_str: str, db: str) -> Dict[str, Any]:
    return await _gather_named(
        {
            "backup_health": diagnostics.backup_health(conn_str, database=db),
            "checkdb_health": diagnostics.checkdb_health(conn_str, database=db),
            "job_health": diagnostics.job_health(conn_str),
        }
    )


@tab("index-buffer")
async def _index_buffer(conn_str: str, db: str) -> Dict[str, Any]:
    return await _gather_named(
        {
            "index_fragmentation": diagnostics.index_fragmentation(conn_str, database=db),
            "unused_indexes": diagnostics.unused_indexes(conn_str, database=db),
            "stale_statistics": diagnostics.stale_statistics(conn_str, database=db),
        }
    )


@tab("ag")
async def _ag(conn_str: str, db: str) -> Dict[str, Any]:
    result = await _gather_named({"ag_health": diagnostics.ag_health(conn_str)})
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
    instance = await _find_instance(instance_name)
    return await builder(instance.mssql_connection_string, database_name)
