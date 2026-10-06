"""Performance implementation."""

from typing import Any, Dict, List, Optional
from app.infrastructure.sqlserver.client import MSSQLError
from app.modules.monitoring.diagnostics.health import _PLAN_HANDLE_RE
from app.modules.monitoring.diagnostics.health import _SQL_QUERY_PLAN
from app.modules.monitoring.diagnostics.common import _filter_top_queries_by_database
from app.modules.monitoring.diagnostics.parsers import _parse_plan_xml
from app.modules.monitoring.diagnostics.common import _query
from app.modules.monitoring.diagnostics.queries import _sql_index_fragmentation
from app.modules.monitoring.diagnostics.queries import _sql_missing_indexes
from app.modules.monitoring.diagnostics.queries import _sql_stale_statistics
from app.modules.monitoring.diagnostics.queries import _sql_top_queries
from app.modules.monitoring.diagnostics.queries import _sql_unused_indexes


async def missing_indexes(connection_string: str, database: Optional[str] = None, top_n: int = 25) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_missing_indexes(top_n), database)


async def unused_indexes(connection_string: str, database: Optional[str] = None, top_n: int = 25) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_unused_indexes(top_n), database)


async def stale_statistics(
    connection_string: str, database: Optional[str] = None, days_threshold: int = 30
) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_stale_statistics(days_threshold), database)


async def index_fragmentation(
    connection_string: str, database: Optional[str] = None, min_frag_pct: float = 5.0, top_n: int = 50
) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_index_fragmentation(min_frag_pct, top_n), database)


async def top_queries(connection_string: str, database: Optional[str] = None, top_n: int = 25) -> List[Dict[str, Any]]:
    sql = _filter_top_queries_by_database(_sql_top_queries(top_n), database)
    return await _query(connection_string, sql)


async def query_plan(connection_string: str, plan_handle: str) -> Dict[str, Any]:
    """Real execution plan for one cached statement, parsed into a
    cost-proportional per-node time breakdown — see _parse_plan_xml's
    docstring for exactly what "real" means here (cost-derived, not
    measured). `plan_handle` must be the hex string top_queries() returns
    (e.g. "0x0500...") — validated strictly since it's embedded directly
    into the query (mssql_client runs fixed, parameter-free SQL)."""
    if not _PLAN_HANDLE_RE.match(plan_handle):
        raise MSSQLError(f"Invalid plan_handle: {plan_handle!r}")

    rows = await _query(connection_string, _SQL_QUERY_PLAN.format(plan_handle=plan_handle))
    if not rows or not rows[0].get("QueryPlanXml"):
        return {"available": False, "nodes": []}

    row = rows[0]
    execution_count = max(int(row.get("ExecutionCount") or 1), 1)
    avg_elapsed_ms = (row.get("TotalElapsedTimeMicros") or 0) / execution_count / 1000.0
    avg_logical_reads = (row.get("TotalLogicalReads") or 0) / execution_count

    return {
        "available": True,
        "execution_count": execution_count,
        "avg_elapsed_ms": round(avg_elapsed_ms, 2),
        "avg_logical_reads": round(avg_logical_reads, 1),
        "nodes": _parse_plan_xml(row["QueryPlanXml"], avg_elapsed_ms),
    }
