"""Common implementation."""

import logging
from typing import Any, Dict, List, Optional, Tuple
from app.infrastructure.sqlserver import client as mssql_client


logger = logging.getLogger(__name__)


def _escape_sql_string(value: str) -> str:
    if not value:
        return "''"
    return "'" + value.replace("'", "''") + "'"


def _rows_to_dicts(columns: List[str], rows: List[Tuple[Any, ...]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for row in rows:
        obj: Dict[str, Any] = {}
        for i, col in enumerate(columns):
            value = row[i] if i < len(row) else None
            if isinstance(value, (bytes, bytearray)):
                # Hex-encoded (e.g. "0xABCD...") rather than an opaque
                # placeholder — plan_handle in particular needs to round-trip
                # through the API as a real, usable identifier (see
                # query_plan()), and a hex string is more useful than
                # "<binary>" for any other varbinary column too.
                obj[col] = "0x" + bytes(value).hex()
            elif hasattr(value, "isoformat"):
                obj[col] = value.isoformat()
            else:
                obj[col] = value
        result.append(obj)
    return result


def _severity_rank(sev: Optional[str]) -> int:
    return {"CRITICAL": 0, "WARNING": 1, "UNKNOWN": 2, "OK": 3}.get(sev or "", 2)


def _worst_severity(rows: List[Dict[str, Any]], default: str = "OK") -> str:
    if not rows:
        return default
    worst = default
    for row in rows:
        sev = row.get("severity") or "UNKNOWN"
        if _severity_rank(sev) < _severity_rank(worst):
            worst = sev
    return worst


def _extract_metric(rows: List[Dict[str, Any]], column: str, agg: str = "max") -> Optional[float]:
    """Pull one representative numeric headline metric out of a diagnostic
    result — e.g. the worst FullBackupAgeHours across all databases. Used
    only for trend-history snapshots (app/modules/monitoring/collector.py); severity remains
    the authority for health status."""
    values = []
    for row in rows:
        v = row.get(column)
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


def _filter_by_database(sql: str, database: Optional[str]) -> str:
    if not database:
        return sql
    anchor = "WHERE d.database_id > 4 AND d.state_desc = 'ONLINE'"
    return sql.replace(anchor, f"{anchor} AND d.name = {_escape_sql_string(database)}")


def _filter_top_queries_by_database(sql: str, database: Optional[str]) -> str:
    if not database:
        return sql
    anchor = "WHERE st.dbid IS NOT NULL"
    return sql.replace(anchor, f"{anchor} AND DB_NAME(st.dbid) = {_escape_sql_string(database)}")


async def _query(connection_string: str, sql: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
    res = await mssql_client.execute_query(connection_string, sql, database=database)
    return _rows_to_dicts(res.columns, res.rows)
