"""
Fleet-wide health rollup — the real evaluated alert logic monitor/'s Grafana
stack never had (its "alerting" was only a provisioned SMTP contact point
with zero actual alert rules; every threshold lived only as a static panel
color).

Severities are computed once, in SQL, by app/diagnostics.py (a direct-SQL
port of the MCP server's diagnostic tools, mcp/src/data_eyes_mcp/dba_tools.py),
driven by .claude/knowledge-base/_static/thresholds.yaml. This module only
aggregates what diagnostics.fleet_health_score already decided — it does not
invent new thresholds of its own.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from . import diagnostics, repository
from .config import InstanceConfig
from .mssql_client import MSSQLError

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"CRITICAL": 0, "WARNING": 1, "UNKNOWN": 2, "OK": 3}


class InstanceHealth(BaseModel):
    name: str
    label: str
    environment: Optional[str] = None
    reachable: bool
    overall_severity: str
    categories: dict = {}
    metrics: dict = {}
    database_count: Optional[int] = None
    database_status: Optional[List[dict]] = None
    error: Optional[str] = None
    # Card-view fields (Fleet Status "Cards" mode) — best-effort: any one of
    # these failing to load never fails the whole instance row, it's just
    # None on the card (see _instance_health's per-call try/except below).
    server: Optional[Dict[str, Any]] = None
    cpu: Optional[Dict[str, Any]] = None
    workers: Optional[Dict[str, Any]] = None
    memory: Optional[Dict[str, Any]] = None
    disk: Optional[Dict[str, Dict[str, Any]]] = None


class FleetHealth(BaseModel):
    overall_severity: str
    instances: List[InstanceHealth]


async def _instance_health(instance: InstanceConfig) -> InstanceHealth:
    async def read_database_status():
        try:
            return await diagnostics.database_status(instance.mssql_connection_string)
        except MSSQLError:
            return None

    async def _safe(coro):
        try:
            return await coro
        except MSSQLError:
            return None

    async def read_card_extras():
        """Best-effort Fleet Cards data — server facts, CPU breakdown,
        worker/memory gauges, and db_space (for per-drive free space; yes,
        fleet_health_score() also queries db_space internally for its own
        severity — a second lightweight per-file query here is an accepted
        duplication rather than restructuring that function to expose raw
        rows). Any one of these failing never fails the instance row; it
        just leaves that card section blank."""
        return await asyncio.gather(
            _safe(diagnostics.server_overview(instance.mssql_connection_string)),
            _safe(diagnostics.resource_utilization(instance.mssql_connection_string)),
            _safe(diagnostics.worker_stats(instance.mssql_connection_string)),
            _safe(diagnostics.memory_stats(instance.mssql_connection_string)),
            _safe(diagnostics.db_space(instance.mssql_connection_string)),
        )

    async def read_errors_severity():
        try:
            return await repository.get_latest_category_severity(instance.name, "errors")
        except repository.RepositoryUnavailable:
            return None

    async def read_drive_io():
        try:
            return await repository.get_latest_drive_io(instance.name)
        except repository.RepositoryUnavailable:
            return {}

    try:
        score, db_list, db_status, card_extras, errors_severity, drive_io = await asyncio.gather(
            diagnostics.fleet_health_score(instance.mssql_connection_string),
            diagnostics.list_databases(instance.mssql_connection_string),
            read_database_status(),
            read_card_extras(),
            read_errors_severity(),
            read_drive_io(),
        )
        database_count = len(db_list) if isinstance(db_list, list) else None
        overall = score.get("overall_severity", "UNKNOWN") if isinstance(score, dict) else "UNKNOWN"
        categories = score.get("categories", {}) if isinstance(score, dict) else {}
        metrics = score.get("metrics", {}) if isinstance(score, dict) else {}
        # "errors" isn't one of fleet_health_score's 8 live-computed
        # categories (it's only meaningful as a delta over time — see
        # diagnostics.error_rate_stats' docstring) — merged in here from the
        # collector's own periodic computation instead.
        if errors_severity:
            categories = {**categories, "errors": errors_severity}

        server_overview, resources, workers, memory, db_space_rows = card_extras

        cpu = None
        if resources:
            cpu = {
                "sql_pct": resources.get("sql_cpu_pct"),
                "os_pct": resources.get("os_cpu_pct"),
                "history": resources.get("cpu_history") or [],
            }

        disk: Dict[str, Dict[str, Any]] = {}
        if isinstance(db_space_rows, list):
            for row in db_space_rows:
                drive = row.get("Drive")
                if not drive or drive in disk:
                    continue
                disk[drive] = {"free_gb": row.get("DriveFreeSpaceGB")}
        for drive, io in (drive_io or {}).items():
            disk.setdefault(drive, {})
            disk[drive].update(io)

        return InstanceHealth(
            name=instance.name,
            label=instance.label,
            environment=instance.environment,
            reachable=True,
            overall_severity=overall,
            categories=categories,
            metrics=metrics,
            database_count=database_count,
            database_status=db_status,
            server=server_overview,
            cpu=cpu,
            workers=workers,
            memory=memory,
            disk=disk or None,
        )
    except MSSQLError as e:
        logger.warning("Instance %s unreachable: %s", instance.name, e)
        return InstanceHealth(
            name=instance.name,
            label=instance.label,
            environment=instance.environment,
            reachable=False,
            overall_severity="UNKNOWN",
            error=str(e),
        )


async def get_fleet_health(instances: List[InstanceConfig]) -> FleetHealth:
    """Fan out to every registered instance in parallel and roll up the worst
    severity across the fleet. One unreachable/slow instance never blocks the
    others — each direct-SQL call has its own timeout (see mssql_client.py's
    DEFAULT_QUERY_TIMEOUT)."""
    if not instances:
        return FleetHealth(overall_severity="UNKNOWN", instances=[])
    results = await asyncio.gather(*(_instance_health(i) for i in instances))
    overall = min(
        (r.overall_severity for r in results), key=lambda s: _SEVERITY_RANK.get(s, 3)
    )
    return FleetHealth(overall_severity=overall, instances=list(results))
