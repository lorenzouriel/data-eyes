"""
Fleet-wide health rollup — the real evaluated alert logic monitor/'s Grafana
stack never had (its "alerting" was only a provisioned SMTP contact point
with zero actual alert rules; every threshold lived only as a static panel
color).

Severities are computed once, in SQL, by the MCP server's diagnostic tools
(mcp/src/data_eyes_mcp/dba_tools.py), driven by
.claude/knowledge-base/_static/thresholds.yaml. This module only aggregates
what those tools already decided via fleet_health_score — it does not invent
new thresholds of its own.
"""

import asyncio
import logging
from typing import List, Optional

from pydantic import BaseModel

from .config import InstanceConfig, settings
from .mcp_client import MCPToolError, call_tool

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"CRITICAL": 0, "WARNING": 1, "OK": 2, "UNKNOWN": 3}


class InstanceHealth(BaseModel):
    name: str
    label: str
    environment: Optional[str] = None
    reachable: bool
    overall_severity: str
    categories: dict = {}
    database_count: Optional[int] = None
    error: Optional[str] = None


class FleetHealth(BaseModel):
    overall_severity: str
    instances: List[InstanceHealth]


async def _instance_health(instance: InstanceConfig) -> InstanceHealth:
    try:
        score, db_list = await asyncio.gather(
            call_tool(instance.mcp_url, "fleet_health_score", timeout=settings.MCP_CALL_TIMEOUT_SECONDS),
            call_tool(instance.mcp_url, "list_databases", timeout=settings.MCP_CALL_TIMEOUT_SECONDS),
        )
        database_count = len(db_list) if isinstance(db_list, list) else None
        overall = score.get("overall_severity", "UNKNOWN") if isinstance(score, dict) else "UNKNOWN"
        categories = score.get("categories", {}) if isinstance(score, dict) else {}
        return InstanceHealth(
            name=instance.name,
            label=instance.label,
            environment=instance.environment,
            reachable=True,
            overall_severity=overall,
            categories=categories,
            database_count=database_count,
        )
    except MCPToolError as e:
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
    others — each call has its own timeout (MCP_CALL_TIMEOUT_SECONDS)."""
    if not instances:
        return FleetHealth(overall_severity="UNKNOWN", instances=[])
    results = await asyncio.gather(*(_instance_health(i) for i in instances))
    overall = min(
        (r.overall_severity for r in results), key=lambda s: _SEVERITY_RANK.get(s, 3)
    )
    return FleetHealth(overall_severity=overall, instances=list(results))
