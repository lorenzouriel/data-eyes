"""
Background severity-change sweep — the "background sweep" half of the
embedded insights agent (rearchitecture plan §4). Runs on a much lower
frequency than the trend collector (minutes, not seconds — see
COLLECTOR_INTERVAL_SECONDS vs INSIGHTS_SWEEP_INTERVAL_SECONDS) and only calls
the LLM when a category's severity actually changed since the previous
sweep, bounding cost against a fleet whose data is otherwise polled
continuously by collector.py.
"""

import asyncio
import logging
from typing import Dict, Optional, Tuple

from . import diagnostics, insights_agent, insights_feed, repository
from .config import settings
from .mssql_client import MSSQLError

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
# In-memory only, matching insights_feed.py — resets on restart, which just
# means the first sweep after a restart never fires an insight (no prior
# severity to compare against), not a correctness problem.
_last_severity: Dict[Tuple[str, str], str] = {}


async def _sweep_instance(instance) -> None:
    try:
        score = await diagnostics.fleet_health_score(instance.mssql_connection_string)
    except MSSQLError as e:
        logger.warning("Insights sweep: instance %s unreachable: %s", instance.name, e)
        return
    if not isinstance(score, dict):
        return

    categories = score.get("categories", {})
    for category, severity in categories.items():
        key = (instance.name, category)
        previous = _last_severity.get(key)
        _last_severity[key] = severity
        if previous is None or previous == severity:
            continue  # first sighting or unchanged — no insight, no LLM call

        message = await insights_agent.generate_severity_change_insight(
            instance.name, category, previous, severity, {"categories": categories}
        )
        if message:
            insights_feed.add_insight(instance.name, category, severity, message)


async def _sweep_once() -> None:
    try:
        instances = await repository.list_instances()
    except repository.RepositoryUnavailable as e:
        logger.warning("Insights sweep: repository unavailable this cycle: %s", e)
        return
    if not instances:
        return
    await asyncio.gather(*(_sweep_instance(i) for i in instances))


async def _run_forever() -> None:
    logger.info(
        "Insights sweep loop starting (interval=%ss)", settings.INSIGHTS_SWEEP_INTERVAL_SECONDS
    )
    while True:
        try:
            await _sweep_once()
        except Exception:
            logger.exception("Insights sweep: unexpected error during sweep cycle")
        await asyncio.sleep(settings.INSIGHTS_SWEEP_INTERVAL_SECONDS)


def start() -> None:
    global _task
    if not settings.ANTHROPIC_API_KEY:
        logger.info("ANTHROPIC_API_KEY not configured — insights sweep disabled")
        return
    if _task is None:
        _task = asyncio.create_task(_run_forever())


def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
