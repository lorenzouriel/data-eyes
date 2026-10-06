"""Fleet implementation."""

from typing import Any, Dict
from app.infrastructure.sqlserver.client import MSSQLError
from app.modules.monitoring.diagnostics.common import _extract_metric
from app.modules.monitoring.diagnostics.common import _query
from app.modules.monitoring.diagnostics.queries import _sql_ag_health
from app.modules.monitoring.diagnostics.queries import _sql_backup_health
from app.modules.monitoring.diagnostics.queries import _sql_blocking_snapshot
from app.modules.monitoring.diagnostics.queries import _sql_checkdb_health
from app.modules.monitoring.diagnostics.queries import _sql_db_space
from app.modules.monitoring.diagnostics.queries import _sql_index_fragmentation
from app.modules.monitoring.diagnostics.queries import _sql_job_health
from app.modules.monitoring.diagnostics.queries import _sql_wait_stats
from app.modules.monitoring.diagnostics.common import _worst_severity
import logging
logger = logging.getLogger(__name__)


async def fleet_health_score(connection_string: str) -> Dict[str, Any]:
    """Aggregate worst-severity rollup across every diagnostic category for
    THIS instance. top_queries is deliberately excluded: slow queries are an
    analysis category, not an operational-risk gate the way disk exhaustion
    or a missed backup is. Also returns one representative numeric headline
    metric per category where one exists, for app/modules/monitoring/collector.py's trend
    snapshots."""
    categories_sql = {
        "wait_stats": _sql_wait_stats(25),
        "index_fragmentation": _sql_index_fragmentation(5.0, 50),
        "db_space": _sql_db_space(),
        "backup_health": _sql_backup_health(),
        "checkdb_health": _sql_checkdb_health(),
        "blocking": _sql_blocking_snapshot(),
        "ag_health": _sql_ag_health(),
        "job_health": _sql_job_health(),
    }
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

    results: Dict[str, str] = {}
    headline_metrics: Dict[str, float] = {}
    for name, sql in categories_sql.items():
        try:
            rows = await _query(connection_string, sql)
            # ag_health legitimately returns nothing on standalone instances —
            # that's OK, not unknown, so it doesn't drag the rollup down.
            results[name] = _worst_severity(rows, default="OK")

            spec = metric_specs.get(name)
            if spec:
                column, agg = spec
                value = _extract_metric(rows, column, agg)
                if value is not None:
                    headline_metrics[f"{name}.{column}"] = value
        except MSSQLError:
            logger.exception("fleet_health_score: category %s failed", name)
            results[name] = "UNKNOWN"

    rank_order = {"CRITICAL": 0, "WARNING": 1, "UNKNOWN": 2, "OK": 3}
    overall = min(results.values(), key=lambda s: rank_order.get(s, 3)) if results else "UNKNOWN"

    return {"overall_severity": overall, "categories": results, "metrics": headline_metrics}
