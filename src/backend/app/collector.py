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
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from . import diagnostics, repository
from .config import settings
from .mssql_client import MSSQLError, query_lane
from .repository import RepositoryUnavailable, insert_snapshot, prune_old_snapshots

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
_activity_task: Optional[asyncio.Task] = None

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
# a rate (see diagnostics.resource_utilization's docstring)
_last_resource_counters: Dict[str, Dict[str, float]] = {}

# Same delta pattern again, for per-file IO stall time/bytes/count
# (sys.dm_io_virtual_file_stats is cumulative and per-file, just like
# sys.dm_os_wait_stats is cumulative and per-wait-type) — keyed by
# (database_name, file_name) per instance; value is (stall_ms, bytes, count).
_last_file_io_totals: Dict[str, Dict[Tuple[str, str], Tuple[float, float, float]]] = {}

# Cumulative meaningful-SQL-error count as of the last cycle, per instance —
# same delta-of-cumulative-counter technique as _last_wait_totals, applied to
# sys.dm_os_performance_counters' Errors/sec family instead of wait stats.
_last_error_totals: Dict[str, float] = {}

# Latest deadlock-event timestamp already persisted per instance, so
# _collect_deadlocks only inserts genuinely new events out of SQL Server's own
# system_health ring buffer each cycle — NOT a delta/baseline like the two
# dicts above: on the very first read for an instance, every event currently
# in the ring buffer is real, already-occurred history, so it's all persisted
# immediately (no "first sample writes nothing" bootstrap here).
_last_deadlock_seen: Dict[str, datetime] = {}


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


async def _collect_activity_sample(instance) -> None:
    """Snapshots the top-50 currently-active sessions (reusing the same query
    the live Sessions tab already runs — no new DMV cost) and appends every
    row to activity_sample. The single log backing Top-10 history for
    Programs/Databases/Machines/DB Users/Plans/SQL Statements, and the query
    drill-down for every other dimension (see repository.get_dimension_log)."""
    try:
        rows = await diagnostics.active_sessions(instance.mssql_connection_string, top_n=50)
    except MSSQLError:
        return
    if not rows:
        return

    samples = []
    for row in rows:
        # pyodbc can return these as decimal.Decimal (not just when falsy —
        # `Decimal('0') or 0.0` happens to coerce to float via the `or`,
        # masking this for an all-zero value, but any genuinely nonzero
        # reading stays a Decimal and can't multiply against a float below).
        wait_seconds = float(row.get("WaitSeconds") or 0.0)
        elapsed_seconds = float(row.get("ElapsedSeconds") or 0.0)
        # State is COALESCE(r.wait_type, r.status, s.status) — only reliably
        # a real wait_type when the session actually has wait time recorded;
        # otherwise it's a request/session status string, not a wait type.
        state = row.get("State") if wait_seconds > 0 else None
        sql_text = (row.get("SqlText") or "").strip()
        if not sql_text and wait_seconds <= 0 and elapsed_seconds <= 0:
            continue  # idle connection: no request, nothing the history charts can use
        query_hash = hashlib.md5(sql_text.encode("utf-8")).hexdigest() if sql_text else None
        samples.append(
            {
                "session_id": row.get("Pid"),
                "database_name": row.get("DatabaseName"),
                "program_name": row.get("ProgramName"),
                "host_name": row.get("HostName"),
                "login_name": row.get("LoginName"),
                "wait_type": state,
                "wait_category": diagnostics.categorize_wait_type(state) if state else None,
                "wait_time_ms": wait_seconds * 1000.0,
                "elapsed_time_ms": elapsed_seconds * 1000.0,
                "plan_handle": row.get("PlanHandle"),
                "query_hash": query_hash,
                "sql_text": sql_text[:2000] if sql_text else None,
            }
        )

    if not samples:
        return
    try:
        await repository.insert_activity_sample(instance.name, samples)
    except RepositoryUnavailable:
        logger.warning("Collector: repository unavailable writing activity sample for %s", instance.name)


async def _collect_file_io(instance) -> None:
    """Same delta-of-cumulative-counter technique as _collect_wait_categories,
    applied to per-file IO stall time/bytes/count — backs the Files/Drives
    Top-10 charts AND the fleet Cards' Disk & IO section (via
    repository.get_latest_drive_io, which reads these deltas back out)."""
    try:
        rows = await diagnostics.file_io_stats(instance.mssql_connection_string)
    except MSSQLError:
        return

    current_totals: Dict[Tuple[str, str], Tuple[float, float, float]] = {}
    drives: Dict[Tuple[str, str], Optional[str]] = {}
    for row in rows:
        db, file_name = row.get("DatabaseName"), row.get("FileName")
        if not db or not file_name:
            continue
        key = (db, file_name)
        current_totals[key] = (
            float(row.get("IoStallMs") or 0.0),
            float(row.get("IoBytes") or 0.0),
            float(row.get("IoCount") or 0.0),
        )
        drives[key] = row.get("Drive")

    previous = _last_file_io_totals.get(instance.name)
    _last_file_io_totals[instance.name] = current_totals
    if previous is None:
        return

    deltas = []
    for key, (stall_total, bytes_total, count_total) in current_totals.items():
        prev_stall, prev_bytes, prev_count = previous.get(key, (stall_total, bytes_total, count_total))
        stall_delta = stall_total - prev_stall
        bytes_delta = bytes_total - prev_bytes
        count_delta = count_total - prev_count
        if stall_delta > 0 or bytes_delta > 0:  # negative = counter reset (restart) — skip
            db, file_name = key
            deltas.append(
                {
                    "database_name": db,
                    "file_name": file_name,
                    "drive": drives.get(key),
                    "io_stall_ms": max(stall_delta, 0.0),
                    "io_bytes": max(bytes_delta, 0.0),
                    "io_count": max(count_delta, 0.0),
                }
            )

    if deltas:
        try:
            await repository.insert_file_io_snapshot(instance.name, deltas)
        except RepositoryUnavailable:
            logger.warning("Collector: repository unavailable writing file-IO history for %s", instance.name)


async def _collect_error_rate(instance) -> None:
    """Delta-of-cumulative-counter for meaningful SQL Server errors (see
    diagnostics.error_rate_stats) — writes a real computed severity via
    insert_category_snapshot, unlike the informational-only resource rates,
    since this backs the fleet Cards' ERRORS health dot."""
    try:
        total = await diagnostics.error_rate_stats(instance.mssql_connection_string)
    except MSSQLError:
        return
    if total is None:
        return

    previous = _last_error_totals.get(instance.name)
    _last_error_totals[instance.name] = total
    if previous is None:
        return

    delta = total - previous
    if delta < 0:  # counter reset (restart) — no baseline to judge severity against
        return

    severity = "CRITICAL" if delta >= 10 else "WARNING" if delta > 0 else "OK"
    try:
        await repository.insert_category_snapshot(instance.name, "errors", severity, delta)
    except RepositoryUnavailable:
        logger.warning("Collector: repository unavailable writing error rate for %s", instance.name)


async def _collect_deadlocks(instance) -> None:
    """Polls SQL Server's own system_health ring buffer (always-on by
    default, no new XE session created) and persists whatever deadlock
    events are newer than the last one already written for this instance."""
    try:
        events = await diagnostics.deadlock_events(instance.mssql_connection_string)
    except MSSQLError:
        return
    if not events:
        return

    last_seen = _last_deadlock_seen.get(instance.name)
    max_seen = last_seen
    new_events = []
    for e in events:
        raw_ts = e.get("occurred_at")
        if not raw_ts:
            continue
        try:
            occurred_at = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if last_seen is not None and occurred_at <= last_seen:
            continue
        new_events.append(e)
        if max_seen is None or occurred_at > max_seen:
            max_seen = occurred_at

    if new_events:
        try:
            await repository.insert_deadlock_events(instance.name, new_events)
        except RepositoryUnavailable:
            # Leave the watermark alone so the next cycle retries these events
            # while they're still in the ring buffer.
            logger.warning("Collector: repository unavailable writing deadlock event(s) for %s", instance.name)
            return

    if max_seen is not None:
        _last_deadlock_seen[instance.name] = max_seen


async def _collect_once() -> None:
    cycle_started = datetime.now(timezone.utc)
    try:
        instances = await repository.list_instances()
    except RepositoryUnavailable as e:
        logger.warning("Collector: repository unavailable this cycle: %s", e)
        return
    try:
        await asyncio.gather(
            *(_collect_instance(i) for i in instances),
            *(_collect_wait_categories(i) for i in instances),
            *(_collect_blocking_event(i) for i in instances),
            *(_collect_resource_rates(i) for i in instances),
            *(_collect_file_io(i) for i in instances),
            *(_collect_deadlocks(i) for i in instances),
            *(_collect_error_rate(i) for i in instances),
        )
        from .notifications import dispatcher
        try:
            await dispatcher.evaluate(since=cycle_started)
        except Exception:
            logger.warning("Collector: notification evaluation unavailable this cycle")
    except RepositoryUnavailable as e:
        logger.warning("Collector: repository unavailable this cycle: %s", e)


async def _run_activity_sampler_forever() -> None:
    """Independent fast-cadence loop for activity_sample, decoupled from the
    main 60s collector cycle above. Every other job reads a cumulative
    counter (wait_stats, file IO, errors) where the delta since last cycle
    is correct regardless of sampling interval. activity_sample instead
    captures point-in-time session state — whether a session happens to be
    actively waiting or executing RIGHT NOW — so its odds of catching
    anything meaningful depend entirely on how often it looks: at 60s, a
    query that runs for a few hundred ms is essentially never caught. This
    loop looks every ACTIVITY_SAMPLE_INTERVAL_SECONDS instead."""
    logger.info("Activity sampler loop starting (interval=%ss)", settings.ACTIVITY_SAMPLE_INTERVAL_SECONDS)
    query_lane.set("background")
    while True:
        try:
            instances = await repository.list_instances()
            if instances:
                await asyncio.gather(*(_collect_activity_sample(i) for i in instances))
        except RepositoryUnavailable as e:
            logger.warning("Activity sampler: repository unavailable this cycle: %s", e)
        except Exception:
            logger.exception("Activity sampler: unexpected error during sampling cycle")
        await asyncio.sleep(settings.ACTIVITY_SAMPLE_INTERVAL_SECONDS)


async def _run_forever() -> None:
    logger.info(
        "Trend-history collector loop starting (interval=%ss, retention=%sd)",
        settings.COLLECTOR_INTERVAL_SECONDS,
        settings.TREND_RETENTION_DAYS,
    )
    query_lane.set("background")
    cycle = 0
    while True:
        try:
            await _collect_once()
            # Prune roughly once an hour's worth of cycles rather than every
            # cycle — it's a DELETE scan, no need to run it on a 60s cadence.
            cycle += 1
            if cycle % max(1, 3600 // max(settings.COLLECTOR_INTERVAL_SECONDS, 1)) == 0:
                for prune_fn, label, days in (
                    (prune_old_snapshots, "metric snapshot(s)", settings.TREND_RETENTION_DAYS),
                    (repository.prune_old_wait_category_snapshots, "wait-category snapshot(s)", settings.TREND_RETENTION_DAYS),
                    (repository.prune_old_blocking_events, "blocking event(s)", settings.TREND_RETENTION_DAYS),
                    (repository.prune_old_activity_samples, "activity sample(s)", settings.ACTIVITY_RETENTION_DAYS),
                    (repository.prune_old_file_io_snapshots, "file-IO snapshot(s)", settings.TREND_RETENTION_DAYS),
                    (repository.prune_old_deadlock_events, "deadlock event(s)", settings.TREND_RETENTION_DAYS),
                ):
                    try:
                        pruned = await prune_fn(days)
                        if pruned:
                            logger.info("Collector: pruned %s %s older than %sd", pruned, label, days)
                    except RepositoryUnavailable:
                        pass
                    except Exception:
                        logger.exception("Collector: pruning failed (%s)", label)
        except Exception:
            logger.exception("Collector: unexpected error during collection cycle")
        await asyncio.sleep(settings.COLLECTOR_INTERVAL_SECONDS)


def start() -> None:
    global _task, _activity_task
    if not settings.REPOSITORY_DSN:
        logger.info("REPOSITORY_DSN not configured — trend-history collector disabled")
        return
    if _task is None:
        _task = asyncio.create_task(_run_forever())
    if _activity_task is None:
        _activity_task = asyncio.create_task(_run_activity_sampler_forever())


def stop() -> None:
    global _task, _activity_task
    if _activity_task is not None:
        _activity_task.cancel()
        _activity_task = None
    if _task is not None:
        _task.cancel()
        _task = None
