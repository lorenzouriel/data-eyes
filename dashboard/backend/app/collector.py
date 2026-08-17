"""
Persistent trend-history collector.

Runs continuously as a background task inside the dashboard backend process
— independent of whether anyone has the UI open, which was the actual
requirement behind "persistent" in the rearchitecture plan's DPA comparison.
It is NOT split into its own container in v1: same reasoning as
insights_agent.py's design in the plan — simplest deployment for now, split
out later only if collection load actually competes with the API's own
request handling.

Every failure mode here is non-fatal to the rest of the app: an unreachable
MCP instance just skips that instance for this cycle (logged, not raised);
an unreachable or unconfigured repository DB means the collector logs once
and keeps retrying on its normal interval — it never takes down the fleet
or tab APIs, which don't depend on it.
"""

import asyncio
import logging
from typing import Optional

from .config import load_instances, settings
from .mcp_client import MCPToolError, call_tool
from .repository import RepositoryUnavailable, insert_snapshot, prune_old_snapshots

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None


async def _collect_instance(instance) -> None:
    try:
        score = await call_tool(
            instance.mcp_url, "fleet_health_score", {}, timeout=settings.MCP_CALL_TIMEOUT_SECONDS
        )
    except MCPToolError as e:
        logger.warning("Collector: instance %s unreachable, skipping this cycle: %s", instance.name, e)
        return

    if not isinstance(score, dict):
        logger.warning("Collector: instance %s returned an unexpected fleet_health_score shape", instance.name)
        return

    overall = score.get("overall_severity", "UNKNOWN")
    categories = score.get("categories", {})
    metrics = score.get("metrics", {})

    try:
        await insert_snapshot(instance.name, overall, categories, metrics)
    except RepositoryUnavailable:
        raise  # let the caller log this once per cycle, not once per instance
    except Exception:
        logger.exception("Collector: failed to write snapshot for %s", instance.name)


async def _collect_once() -> None:
    instances = load_instances()
    if not instances:
        return
    try:
        await asyncio.gather(*(_collect_instance(i) for i in instances))
    except RepositoryUnavailable as e:
        logger.warning("Collector: repository unavailable this cycle: %s", e)


async def _run_forever() -> None:
    logger.info(
        "Trend-history collector loop starting (interval=%ss, retention=%sd)",
        settings.COLLECTOR_INTERVAL_SECONDS,
        settings.TREND_RETENTION_DAYS,
    )
    cycle = 0
    while True:
        try:
            await _collect_once()
            # Prune roughly once an hour's worth of cycles rather than every
            # cycle — it's a DELETE scan, no need to run it on a 60s cadence.
            cycle += 1
            if cycle % max(1, 3600 // max(settings.COLLECTOR_INTERVAL_SECONDS, 1)) == 0:
                try:
                    pruned = await prune_old_snapshots(settings.TREND_RETENTION_DAYS)
                    if pruned:
                        logger.info("Collector: pruned %s snapshot(s) older than %sd", pruned, settings.TREND_RETENTION_DAYS)
                except RepositoryUnavailable:
                    pass
                except Exception:
                    logger.exception("Collector: pruning failed")
        except Exception:
            logger.exception("Collector: unexpected error during collection cycle")
        await asyncio.sleep(settings.COLLECTOR_INTERVAL_SECONDS)


def start() -> None:
    global _task
    if not settings.REPOSITORY_DSN:
        logger.info("REPOSITORY_DSN not configured — trend-history collector disabled")
        return
    if _task is None:
        _task = asyncio.create_task(_run_forever())


def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
