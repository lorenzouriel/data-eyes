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
SQL Server just skips that instance for this cycle (logged, not raised); an
unreachable or unconfigured repository DB means the collector logs once and
keeps retrying on its normal interval — it never takes down the fleet or tab
APIs, which don't depend on it.
"""

import asyncio
import logging
from typing import Dict, Optional

from . import diagnostics, repository
from .config import settings
from .mssql_client import MSSQLError
from .repository import RepositoryUnavailable, insert_snapshot, prune_old_snapshots

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None

# Cumulative wait-seconds-per-category as of the last cycle, per instance —
# in-memory only (resets on restart, same shape as insights_sweep.py's
# _last_severity). sys.dm_os_wait_stats is cumulative since server
# restart/last DBCC SQLPERF CLEAR, so the delta between two consecutive
# samples is the real number of seconds accumulated during that interval —
# that delta, not the raw cumulative total, is what the Waits tab's 24h
# chart needs. The first sample after every backend restart establishes a
# baseline and writes nothing (no prior sample to diff against), same
# "first sighting, no output yet" convention insights_sweep.py already uses.
_last_wait_totals: Dict[str, Dict[str, float]] = {}

# Same idea, for the two Resources-tab counters that are only meaningful as
# a rate (see diagnostics.resource_utilization's docstring): raw cumulative
# value as of the last cycle, per instance.
_last_resource_counters: Dict[str, Dict[str, float]] = {}


async def _collect_instance(instance) -> None:
    try:
        score = await diagnostics.fleet_health_score(instance.mssql_connection_string)
    except MSSQLError as e:
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


async def _collect_wait_categories(instance) -> None:
    try:
        # A generous top_n (the function's own max) so this samples close to
        # the full non-benign wait-type set, not just the ~25 rows a tab
        # render needs — a wait type dropping in/out of a smaller top-N
        # window between cycles would corrupt the delta.
        rows = await diagnostics.wait_stats(instance.mssql_connection_string, top_n=200)
    except MSSQLError:
        return

    current_totals: Dict[str, float] = {}
    for row in rows:
        category = row.get("Category") or "other"
        seconds = row.get("Wait_Time_Seconds") or 0.0
        current_totals[category] = current_totals.get(category, 0.0) + float(seconds)

    previous = _last_wait_totals.get(instance.name)
    _last_wait_totals[instance.name] = current_totals
    if previous is None:
        return

    deltas: Dict[str, float] = {}
    for category, total in current_totals.items():
        prev_total = previous.get(category, total)
        delta = total - prev_total
        # Negative delta means the cumulative counter was reset (a restart
        # or DBCC SQLPERF('sys.dm_os_wait_stats', CLEAR) since last cycle) —
        # skip it rather than recording a nonsensical negative wait time.
        if delta > 0:
            deltas[category] = delta

    if deltas:
        try:
            await repository.insert_wait_category_snapshot(instance.name, deltas)
        except RepositoryUnavailable:
            logger.warning("Collector: repository unavailable writing wait-category history for %s", instance.name)


async def _collect_resource_rates(instance) -> None:
    """Disk read rate and batch requests/sec are cumulative SQL Server
    counters — only meaningful as a rate, which needs two samples. This is
    that second sample: diff against last cycle's raw totals (interval =
    COLLECTOR_INTERVAL_SECONDS) and persist the resulting rate."""
    try:
        res = await diagnostics.resource_utilization(instance.mssql_connection_string)
    except MSSQLError:
        return

    current = {
        "disk_io": res.get("disk_read_bytes_total"),
        "batch_requests": res.get("batch_requests_total"),
    }
    previous = _last_resource_counters.get(instance.name)
    _last_resource_counters[instance.name] = {k: v for k, v in current.items() if v is not None}
    if previous is None:
        return

    interval = max(settings.COLLECTOR_INTERVAL_SECONDS, 1)
    for category, total in current.items():
        prev_total = previous.get(category)
        if total is None or prev_total is None or total < prev_total:
            continue  # missing counter, or a reset since last cycle
        rate = (total - prev_total) / interval
        if category == "disk_io":
            rate = rate / (1024 * 1024)  # bytes/sec -> MB/sec
        try:
            await repository.insert_resource_rate(instance.name, category, rate)
        except RepositoryUnavailable:
            logger.warning("Collector: repository unavailable writing %s rate for %s", category, instance.name)


async def _collect_blocking_event(instance) -> None:
    try:
        rows = await diagnostics.blocking_snapshot(instance.mssql_connection_string)
    except MSSQLError:
        return
    if not rows:
        return  # clear this cycle — append-only log, nothing to write

    # blocking_snapshot() returns one row per *blocked* session; there's no
    # row for the root blocker's own statement unless it is itself blocked.
    # The worst-waiting row is the most representative single fact to log
    # for "something was blocked at this timestamp" — a full chain
    # reconstruction happens client-side from the live snapshot (Blocking
    # tab), this log is just the historical "it happened, here's a sample"
    # record.
    worst = max(rows, key=lambda r: r.get("WaitTimeSeconds") or 0.0)
    try:
        await repository.insert_blocking_event(
            instance_name=instance.name,
            root_sql=worst.get("BlockedQueryText"),
            lock_type=worst.get("WaitResource"),
            blocked_count=len(rows),
            duration_seconds=float(worst.get("WaitTimeSeconds") or 0.0),
        )
    except RepositoryUnavailable:
        logger.warning("Collector: repository unavailable writing blocking event for %s", instance.name)


async def _collect_once() -> None:
    try:
        instances = await repository.list_instances()
    except RepositoryUnavailable as e:
        logger.warning("Collector: repository unavailable this cycle: %s", e)
        return
    if not instances:
        return
    try:
        await asyncio.gather(
            *(_collect_instance(i) for i in instances),
            *(_collect_wait_categories(i) for i in instances),
            *(_collect_blocking_event(i) for i in instances),
            *(_collect_resource_rates(i) for i in instances),
        )
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
                for prune_fn, label in (
                    (prune_old_snapshots, "metric snapshot(s)"),
                    (repository.prune_old_wait_category_snapshots, "wait-category snapshot(s)"),
                    (repository.prune_old_blocking_events, "blocking event(s)"),
                ):
                    try:
                        pruned = await prune_fn(settings.TREND_RETENTION_DAYS)
                        if pruned:
                            logger.info("Collector: pruned %s %s older than %sd", pruned, label, settings.TREND_RETENTION_DAYS)
                    except RepositoryUnavailable:
                        pass
                    except Exception:
                        logger.exception("Collector: pruning failed (%s)", label)
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
