"""
Repository-trend tools for Data Eyes MCP Server.

Registers additional @mcp.tool() functions on the same FastMCP instance
created in tools.py, giving an MCP client (Claude Code's sql-server-dba
agent) read access to the Data Eyes dashboard's own trend-history repository
(dashboard/repository/init.sql) — a Postgres database, never a monitored SQL
Server. This answers a different question than dba_tools.py's live-DMV
tools: "how has this instance's severity trended over time" rather than
"what does this instance look like right now."

Every tool here degrades to a clear "not configured" message (never an
error) when REPOSITORY_DSN is unset — same graceful-degradation shape used
throughout the dashboard's own repository.py.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg

from .config import settings
from .tools import mcp
from .utils import format_json

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None

_NOT_CONFIGURED = (
    "Repository not configured on this MCP server (REPOSITORY_DSN unset) — "
    "dashboard trend tools are unavailable."
)


async def _get_pool() -> Optional[asyncpg.Pool]:
    global _pool
    if not settings.REPOSITORY_DSN:
        return None
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(settings.REPOSITORY_DSN, min_size=1, max_size=3)
        except Exception:
            logger.exception("Could not connect to the dashboard repository")
            return None
    return _pool


@mcp.tool()
async def list_tracked_instances() -> str:
    """
    List every instance registered in the Data Eyes dashboard's own instance
    registry — reads the dashboard's repository database, not a live SQL
    Server query. Use this to discover valid `instance_name` values for
    get_severity_trend / get_latest_snapshot.

    Returns:
        JSON list of {name, label, environment}, or a message if
        REPOSITORY_DSN isn't configured on this MCP server.
    """
    pool = await _get_pool()
    if pool is None:
        return _NOT_CONFIGURED
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT name, label, environment FROM instance ORDER BY name")
    except Exception as e:
        logger.exception("list_tracked_instances failed")
        return f"ERROR: {type(e).__name__}: {e}"
    if not rows:
        return "No instances registered in the dashboard."
    columns = ["name", "label", "environment"]
    data = [tuple(row[c] for c in columns) for row in rows]
    return format_json(columns, data)


@mcp.tool()
async def get_severity_trend(instance_name: str, category: str, hours: int = 24) -> str:
    """
    Severity/metric history for one instance+category from the dashboard's
    trend-history repository (collected on the dashboard backend's own
    interval — see COLLECTOR_INTERVAL_SECONDS there) — not a live query. Use
    list_tracked_instances for valid instance_name values, and
    .claude/knowledge-base/_static/taxonomy.md for valid category names
    (plus the synthetic "overall" category for the instance's rolled-up
    severity).

    Args:
        instance_name: An instance name from list_tracked_instances.
        category: A diagnostic category, e.g. "wait_stats", "db_space",
            "backup_health", or "overall".
        hours: Lookback window (default 24, max 720).

    Returns:
        JSON list of {captured_at, severity, metric_value}, oldest first, or
        a message if REPOSITORY_DSN isn't configured or there's no history yet.
    """
    pool = await _get_pool()
    if pool is None:
        return _NOT_CONFIGURED
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, min(hours, 24 * 30)))
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT captured_at, severity, metric_value
                FROM metric_snapshot
                WHERE instance_name = $1 AND category = $2 AND captured_at >= $3
                ORDER BY captured_at ASC
                """,
                instance_name,
                category,
                since,
            )
    except Exception as e:
        logger.exception("get_severity_trend failed")
        return f"ERROR: {type(e).__name__}: {e}"
    if not rows:
        return f"No trend history for instance={instance_name!r} category={category!r} in the last {hours}h."
    columns = ["captured_at", "severity", "metric_value"]
    data = [tuple(row[c] for c in columns) for row in rows]
    return format_json(columns, data)


@mcp.tool()
async def get_latest_snapshot(instance_name: str) -> str:
    """
    Most recent severity + headline metric per category for one instance, as
    of the dashboard's last collection cycle — not a live query (may be up
    to COLLECTOR_INTERVAL_SECONDS stale). For live, current-moment data, use
    this server's own live-SQL tools (wait_stats, fleet_health_score, etc.)
    against the actual SQL Server instead.

    Args:
        instance_name: An instance name from list_tracked_instances.

    Returns:
        JSON list of {category, severity, metric_value, captured_at}, one
        row per category, or a message if REPOSITORY_DSN isn't configured or
        nothing has been collected for this instance yet.
    """
    pool = await _get_pool()
    if pool is None:
        return _NOT_CONFIGURED
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (category) category, severity, metric_value, captured_at
                FROM metric_snapshot
                WHERE instance_name = $1
                ORDER BY category, captured_at DESC
                """,
                instance_name,
            )
    except Exception as e:
        logger.exception("get_latest_snapshot failed")
        return f"ERROR: {type(e).__name__}: {e}"
    if not rows:
        return f"No snapshots collected yet for instance={instance_name!r}."
    columns = ["category", "severity", "metric_value", "captured_at"]
    data = [tuple(row[c] for c in columns) for row in rows]
    return format_json(columns, data)
