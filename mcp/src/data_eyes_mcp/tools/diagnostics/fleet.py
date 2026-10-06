"""Fleet implementation."""

from typing import Dict, Optional
from mcp.server.fastmcp import Context
from data_eyes_mcp.observability.metrics import MetricsContext
from data_eyes_mcp.tools.registry import mcp
from data_eyes_mcp.tools.diagnostics.common import _extract_metric
from data_eyes_mcp.tools.diagnostics.common import _run
from data_eyes_mcp.tools.diagnostics.queries import _sql_ag_health
from data_eyes_mcp.tools.diagnostics.queries import _sql_backup_health
from data_eyes_mcp.tools.diagnostics.queries import _sql_blocking_snapshot
from data_eyes_mcp.tools.diagnostics.queries import _sql_checkdb_health
from data_eyes_mcp.tools.diagnostics.queries import _sql_db_space
from data_eyes_mcp.tools.diagnostics.queries import _sql_index_fragmentation
from data_eyes_mcp.tools.diagnostics.queries import _sql_job_health
from data_eyes_mcp.tools.diagnostics.queries import _sql_wait_stats
from data_eyes_mcp.tools.diagnostics.common import _worst_severity
import logging
logger = logging.getLogger(__name__)


@mcp.tool()
async def fleet_health_score(instance: Optional[str] = None, ctx: Optional[Context] = None) -> str:
    """
    Aggregate worst-severity rollup across every diagnostic category for THIS
    instance (wait stats, index fragmentation, disk space, backup, CHECKDB,
    blocking, AG, jobs). True fleet-wide (multi-instance) aggregation happens
    one level up, in the caller (e.g. the dashboard backend fanning out
    across multiple MCP instances) — this tool only ever sees the single
    instance it's connected to. top_queries is deliberately excluded: slow
    queries are an analysis category, not an operational-risk gate the way
    disk exhaustion or a missed backup is.

    Also returns one representative numeric "headline metric" per category
    where one exists (e.g. backup_health's worst FullBackupAgeHours, db_space's
    lowest DriveFreeSpaceGB) — supplementary to severity, used by the
    dashboard's trend-history collector (dashboard/backend/app/modules/monitoring/collector.py)
    to chart a number over time, not just a status color.

    Returns:
        JSON object: {"overall_severity": ..., "categories": {name: severity, ...},
        "metrics": {"category.column": value, ...}} (metrics omitted where no
        representative numeric column applies or no rows were returned).
    """
    with MetricsContext("fleet_health_score") as metrics_ctx:
        try:
            categories = {
                "wait_stats": _sql_wait_stats(25),
                "index_fragmentation": _sql_index_fragmentation(5.0, 50),
                "db_space": _sql_db_space(),
                "backup_health": _sql_backup_health(),
                "checkdb_health": _sql_checkdb_health(),
                "blocking": _sql_blocking_snapshot(),
                "ag_health": _sql_ag_health(),
                "job_health": _sql_job_health(),
            }
            # (column, aggregation) for each category's headline metric.
            metric_specs = {
                "wait_stats": ("Percentage_WaitTime", "max"),
                "index_fragmentation": ("FragmentationPct", "max"),
                "db_space": ("DriveFreeSpaceGB", "min"),
                "backup_health": ("FullBackupAgeHours", "max"),
                "checkdb_health": ("DaysSinceLastCheckDB", "max"),
                "blocking": ("WaitTimeSeconds", "max"),
                "ag_health": ("RedoQueueKB", "max"),
                "job_health": ("FailuresLast7Days", "max"),
            }

            results = {}
            headline_metrics: Dict[str, float] = {}
            for name, sql in categories.items():
                try:
                    res = await _run(sql, None, ctx, instance)
                    # ag_health legitimately returns nothing on standalone instances —
                    # that's OK, not unknown, so it doesn't drag the rollup down.
                    default = "OK"
                    results[name] = _worst_severity(res.columns, res.rows, default=default)

                    spec = metric_specs.get(name)
                    if spec:
                        column, agg = spec
                        value = _extract_metric(res.columns, res.rows, column, agg)
                        if value is not None:
                            headline_metrics[f"{name}.{column}"] = value
                except Exception:
                    logger.exception("fleet_health_score: category %s failed", name)
                    results[name] = "UNKNOWN"

            rank_order = {"CRITICAL": 0, "WARNING": 1, "OK": 2, "UNKNOWN": 3}
            overall = min(results.values(), key=lambda s: rank_order.get(s, 3)) if results else "UNKNOWN"

            metrics_ctx.set_rows(len(results))
            import json as _json
            return _json.dumps(
                {"overall_severity": overall, "categories": results, "metrics": headline_metrics},
                indent=2,
            )
        except Exception as e:
            logger.exception("fleet_health_score failed")
            return f"ERROR: {type(e).__name__}: {str(e)}"
