"""Activity implementation."""

from typing import Any, Dict, List, Optional
from app.modules.monitoring.diagnostics.health import _SQL_HEALTH_RING_BUFFER
from app.modules.monitoring.diagnostics.health import _WAIT_CATEGORY_PREFIXES
from app.modules.monitoring.diagnostics.parsers import _parse_deadlock_events
from app.modules.monitoring.diagnostics.common import _query
from app.modules.monitoring.diagnostics.queries import _sql_active_sessions
from app.modules.monitoring.diagnostics.queries import _sql_blocking_snapshot
from app.modules.monitoring.diagnostics.queries import _sql_wait_stats


async def wait_stats(connection_string: str, database: Optional[str] = None, top_n: int = 25) -> List[Dict[str, Any]]:
    rows = await _query(connection_string, _sql_wait_stats(top_n), database)
    for row in rows:
        row["Category"] = categorize_wait_type(str(row.get("Wait_Type", "")))
    return rows


async def blocking_snapshot(connection_string: str) -> List[Dict[str, Any]]:
    return await _query(connection_string, _sql_blocking_snapshot())


def categorize_wait_type(wait_type: str) -> str:
    """Buckets a raw sys.dm_os_wait_stats wait_type into the 4 coarse
    categories the Waits tab groups by (lock / disk / cpu / network) where a
    prefix is recognized. Anything else is surfaced as the actual wait_type
    — never collapsed into a generic "other" bucket, since that hid
    whatever was really driving wait time behind an opaque catch-all. Shared
    by wait_stats' category column and app/modules/monitoring/collector.py's historical
    wait-category sampling — one taxonomy, not two."""
    for prefixes, category in _WAIT_CATEGORY_PREFIXES:
        if any(wait_type.startswith(p) for p in prefixes):
            return category
    return wait_type


async def active_sessions(connection_string: str, top_n: int = 50) -> List[Dict[str, Any]]:
    """Connected user sessions, including idle connections — not a history;
    call again to see how it's changed. Same DMV family as blocking_snapshot,
    without the blocking filter."""
    return await _query(connection_string, _sql_active_sessions(top_n))


async def deadlock_events(connection_string: str) -> List[Dict[str, Any]]:
    """Deadlock graphs currently held in SQL Server's own system_health
    Extended Events ring buffer (always-on by default — no new XE session is
    created, this only reads one that already exists) — read-only, same
    DMV-only philosophy as everything else in this module. The ring buffer
    has limited capacity and rolls over, so app/modules/monitoring/collector.py polls this and
    persists new events into deadlock_event for durable history."""
    rows = await _query(connection_string, _SQL_HEALTH_RING_BUFFER)
    if not rows or not rows[0].get("TargetData"):
        return []
    return _parse_deadlock_events(rows[0]["TargetData"])
