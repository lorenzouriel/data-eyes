"""Performance implementation."""

from typing import Optional
from mcp.server.fastmcp import Context
from data_eyes_mcp.observability.metrics import MetricsContext
from data_eyes_mcp.tools.registry import mcp
from data_eyes_mcp.core.formatting import format_json
from data_eyes_mcp.tools.diagnostics.common import _filter_top_queries_by_database
from data_eyes_mcp.tools.diagnostics.common import _run
from data_eyes_mcp.tools.diagnostics.queries import _sql_blocking_snapshot
from data_eyes_mcp.tools.diagnostics.queries import _sql_index_fragmentation
from data_eyes_mcp.tools.diagnostics.queries import _sql_missing_indexes
from data_eyes_mcp.tools.diagnostics.queries import _sql_stale_statistics
from data_eyes_mcp.tools.diagnostics.queries import _sql_top_queries
from data_eyes_mcp.tools.diagnostics.queries import _sql_unused_indexes
from data_eyes_mcp.tools.diagnostics.queries import _sql_wait_stats
import logging
logger = logging.getLogger(__name__)


@mcp.tool()
async def wait_stats(database: Optional[str] = None, top_n: int = 25, instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Analyze SQL Server wait statistics to identify performance bottlenecks.

    Cumulative since last restart / DBCC SQLPERF CLEAR — short-uptime instances
    show noisy percentages. Mirrors .claude/resources/performance/additional_queries/wait_statistics.json.sql.

    Args:
        database: Initial catalog for the connection (waits are instance-wide).
        top_n: Max rows to return (default 25, max 200).

    Returns:
        JSON rows: Wait_Type, Wait_Time_Seconds, Waiting_Tasks_Count,
        Percentage_WaitTime, severity.
    """
    with MetricsContext("wait_stats") as metrics:
        try:
            res = await _run(_sql_wait_stats(top_n), database, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No significant wait statistics found."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("wait_stats failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def missing_indexes(database: Optional[str] = None, top_n: int = 25, instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Identify missing indexes by estimated impact, with generated CREATE INDEX text.

    Mirrors .claude/resources/performance/additional_queries/missing_indexes.json.sql. Impact
    thresholds are heuristic — see .claude/knowledge-base/_static/thresholds.yaml.

    Args:
        database: Database to analyze (defaults to the connection's database).
        top_n: Max rows to return (default 25, max 200).

    Returns:
        JSON rows: DatabaseID, Avg_Estimated_Impact, Last_User_Seek, TableName,
        Create_Statement, severity.
    """
    with MetricsContext("missing_indexes") as metrics:
        try:
            res = await _run(_sql_missing_indexes(top_n), database, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No missing indexes reported for this database."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("missing_indexes failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def unused_indexes(database: Optional[str] = None, top_n: int = 25, instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Identify unused nonclustered indexes, with generated DROP INDEX text.

    Caveat: sys.dm_db_index_usage_stats resets on service restart — cross-check
    instance uptime before treating a result here as conclusive. Mirrors
    .claude/resources/performance/additional_queries/unused_indexes.json.sql.

    Args:
        database: Database to analyze (defaults to the connection's database).
        top_n: Max rows to return (default 25, max 200).

    Returns:
        JSON rows: ObjectName, IndexName, IndexID, UserSeek, UserScans,
        UserLookups, UserUpdates, TableRows, Drop_Statement, severity.
    """
    with MetricsContext("unused_indexes") as metrics:
        try:
            res = await _run(_sql_unused_indexes(top_n), database, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No unused indexes found for this database."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("unused_indexes failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def stale_statistics(
    database: Optional[str] = None,
    days_threshold: int = 30,
    instance: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> str:
    """
    Find statistics that are stale (old + modified since last update).

    Mirrors .claude/resources/performance/additional_queries/update_statistics.json.sql (the
    read-only analysis half — running sp_updatestats itself is a write
    operation and stays in that original script / .claude/resources/maintenance/).

    Args:
        database: Database to analyze (defaults to the connection's database).
        days_threshold: WARNING threshold in days (default 30, matches
            .claude/knowledge-base/_static/thresholds.yaml index.stats_staleness_days).

    Returns:
        JSON rows: TableName, ColumnName, StatName, LastUpdated, DaysOld,
        ModificationCounter, severity.
    """
    with MetricsContext("stale_statistics") as metrics:
        try:
            res = await _run(_sql_stale_statistics(days_threshold), database, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No statistics found for this database."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("stale_statistics failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def index_fragmentation(
    database: Optional[str] = None,
    min_frag_pct: float = 5.0,
    top_n: int = 50,
    instance: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> str:
    """
    Live index fragmentation scan (sys.dm_db_index_physical_stats), distinct
    from unused_indexes (usage-stats based). Not a cheap query on large
    databases — don't poll on a short interval. Mirrors
    .claude/resources/maintenance/diagnostics/fragmentation_live_scan.sql.

    Args:
        database: Database to scan (defaults to the connection's database —
            the underlying DMV requires a specific database context).
        min_frag_pct: Minimum fragmentation % to include (default 5.0).
        top_n: Max rows to return (default 50, max 500).

    Returns:
        JSON rows: DatabaseName, TableName, IndexName, IndexType,
        FragmentationPct, PageCount, severity, RecommendedAction.
    """
    with MetricsContext("index_fragmentation") as metrics:
        try:
            res = await _run(_sql_index_fragmentation(min_frag_pct, top_n), database, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No indexes found above the fragmentation threshold."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("index_fragmentation failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def top_queries(database: Optional[str] = None, top_n: int = 25, instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Rank queries by average elapsed time per execution — the "Top SQL"
    DPA-style category. Mirrors .claude/resources/performance/additional_queries/top_queries.json.sql,
    which closed a gap where this logic previously only existed as inline
    Grafana panel SQL.

    Args:
        database: Restrict to queries whose plan is attributed to this
            database (defaults to all databases in the plan cache).
        top_n: Max rows to return (default 25, max 200).

    Returns:
        JSON rows: DatabaseName, ExecutionCount, AvgElapsedTimeMs,
        AvgCpuTimeMs, AvgLogicalReads, MaxElapsedTimeMs, LastExecutionTime,
        QueryText, severity.
    """
    with MetricsContext("top_queries") as metrics:
        try:
            sql = _filter_top_queries_by_database(_sql_top_queries(top_n), database)
            res = await _run(sql, None, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No query stats found in the plan cache."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("top_queries failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"


@mcp.tool()
async def blocking_snapshot(instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Point-in-time snapshot of active blocking, instance-wide, with head-blocker
    identification. This is a snapshot, not a trend — call repeatedly to detect
    persistent vs. transient blocking. Mirrors
    .claude/resources/maintenance/diagnostics/blocking_chain_snapshot.sql.

    Returns:
        JSON rows: BlockedSessionID, BlockingSessionID, WaitType,
        WaitTimeSeconds, WaitResource, DatabaseName, BlockedLoginName,
        BlockedHostName, BlockedQueryText, BlockingSessionIsHeadBlocker, severity.
    """
    with MetricsContext("blocking_snapshot") as metrics:
        try:
            res = await _run(_sql_blocking_snapshot(), None, ctx, instance)
            metrics.set_rows(len(res.rows))
            if not res.rows:
                return "No active blocking detected."
            return format_json(res.columns, res.rows)
        except Exception as e:
            logger.exception("blocking_snapshot failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"
