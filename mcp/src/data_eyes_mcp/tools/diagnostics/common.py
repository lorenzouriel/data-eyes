"""Common implementation."""

import logging
from typing import Any, List, Optional, Tuple
from mcp.server.fastmcp import Context
from data_eyes_mcp.database.client import QueryResult
from data_eyes_mcp.database.client import execute_query
from data_eyes_mcp.database.client import request_credentials
from data_eyes_mcp.transport.context import _connection_options
from data_eyes_mcp.core.formatting import escape_sql_string


logger = logging.getLogger(__name__)


def _severity_rank(sev: Optional[str]) -> int:
    return {"CRITICAL": 0, "WARNING": 1, "OK": 2}.get(sev or "", 3)


def _worst_severity(columns: List[str], rows: List[Tuple[Any, ...]], default: str = "OK") -> str:
    """Worst `severity` value across rows; `default` if the column/rows are absent."""
    if "severity" not in columns or not rows:
        return default
    idx = columns.index("severity")
    worst = default
    for row in rows:
        sev = row[idx]
        if _severity_rank(sev) < _severity_rank(worst):
            worst = sev
    return worst


def _extract_metric(
    columns: List[str], rows: List[Tuple[Any, ...]], column: str, agg: str = "max"
) -> Optional[float]:
    """Pull one representative numeric headline metric out of a diagnostic
    tool's rows — e.g. the worst FullBackupAgeHours across all databases.
    Used only for trend-history snapshots (dashboard/backend/app/modules/monitoring/collector.py);
    severity remains the authority for health status, this is supplementary
    context for charting a number over time alongside it."""
    if column not in columns or not rows:
        return None
    idx = columns.index(column)
    values = []
    for row in rows:
        v = row[idx]
        if v is None:
            continue
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            continue
    if not values:
        return None
    if agg == "min":
        return min(values)
    if agg == "count":
        return float(len(values))
    return max(values)


async def _run(
    sql: str,
    database: Optional[str],
    ctx: Optional[Context],
    instance: Optional[str] = None,
) -> QueryResult:
    with request_credentials(**_connection_options(ctx, instance)):
        return await execute_query(sql, database=database)


def _filter_by_database(sql: str, database: Optional[str]) -> str:
    """Append an exact-name filter to the shared WHERE clause anchor used by
    _sql_backup_health / _sql_checkdb_health / _sql_db_space (all scan every
    user database by default; this narrows to one when the caller passes
    `database`)."""
    if not database:
        return sql
    anchor = "WHERE d.database_id > 4 AND d.state_desc = 'ONLINE'"
    return sql.replace(anchor, f"{anchor} AND d.name = {escape_sql_string(database)}")


def _filter_top_queries_by_database(sql: str, database: Optional[str]) -> str:
    """Same idea as _filter_by_database, scoped to _sql_top_queries' own
    WHERE clause anchor (a different shape since it filters plan-cache
    entries by dbid, not sys.databases rows)."""
    if not database:
        return sql
    anchor = "WHERE st.dbid IS NOT NULL"
    return sql.replace(anchor, f"{anchor} AND DB_NAME(st.dbid) = {escape_sql_string(database)}")
