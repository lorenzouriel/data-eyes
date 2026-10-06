"""Repository implementation."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.infrastructure.postgres.pool import RepositoryUnavailable
from app.infrastructure.postgres.pool import _acquire
from app.infrastructure.postgres.pool import _invalidate_pool_on_failure


async def insert_snapshot(
    instance_name: str,
    overall_severity: str,
    categories: Dict[str, str],
    metrics: Dict[str, float],
) -> None:
    """One row per category, plus a synthetic "overall" row so the Main Page
    fleet card can show an instance-level trend without picking one category
    to stand in for the whole instance."""
    captured_at = datetime.now(timezone.utc)

    rows = [(captured_at, instance_name, overall_severity, "overall", overall_severity, None)]
    for category, severity in categories.items():
        metric_value = next(
            (value for key, value in metrics.items() if key.startswith(f"{category}.")), None
        )
        rows.append((captured_at, instance_name, overall_severity, category, severity, metric_value))

    try:
        async with await _acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO metric_snapshot
                    (captured_at, instance_name, overall_severity, category, severity, metric_value)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                rows,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Snapshot insert failed: {e}") from e


async def prune_old_snapshots(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM metric_snapshot WHERE captured_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Prune failed: {e}") from e
    # asyncpg returns a string like "DELETE 42" — pull the row count back out.
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def get_trend(instance_name: str, category: str, since_hours: int = 24) -> List[Dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    try:
        async with await _acquire() as conn:
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
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Trend query failed: {e}") from e
    return [
        {
            "captured_at": row["captured_at"].isoformat(),
            "severity": row["severity"],
            "metric_value": row["metric_value"],
        }
        for row in rows
    ]


async def insert_resource_rate(instance_name: str, category: str, metric_value: float) -> None:
    """Reuses metric_snapshot for the two Resources-tab metrics that are only
    meaningful as a rate (disk read MB/s, batch requests/sec — see
    app/modules/monitoring/collector.py). severity is fixed to "OK": these are informational,
    not operational-risk gates with a threshold band the way backup/CHECKDB
    are, so they're written outside fleet_health_score's rollup (same
    reasoning top_queries is already excluded from it)."""
    captured_at = datetime.now(timezone.utc)
    try:
        async with await _acquire() as conn:
            await conn.execute(
                """
                INSERT INTO metric_snapshot
                    (captured_at, instance_name, overall_severity, category, severity, metric_value)
                VALUES ($1, $2, 'OK', $3, 'OK', $4)
                """,
                captured_at,
                instance_name,
                category,
                metric_value,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Resource-rate insert failed: {e}") from e


async def insert_wait_category_snapshot(instance_name: str, category_seconds: Dict[str, float]) -> None:
    """One row per category this cycle — category_seconds is the delta
    since the previous cycle (see app/modules/monitoring/collector.py), already computed by
    the caller; this function just persists it."""
    if not category_seconds:
        return
    captured_at = datetime.now(timezone.utc)
    rows = [(captured_at, instance_name, category, seconds) for category, seconds in category_seconds.items()]
    try:
        async with await _acquire() as conn:
            await conn.executemany(
                "INSERT INTO wait_category_snapshot (captured_at, instance_name, category, seconds) "
                "VALUES ($1, $2, $3, $4)",
                rows,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Wait-category snapshot insert failed: {e}") from e


async def get_wait_category_history(instance_name: str, since_hours: int = 24) -> List[Dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    try:
        async with await _acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT captured_at, category, seconds
                FROM wait_category_snapshot
                WHERE instance_name = $1 AND captured_at >= $2
                ORDER BY captured_at ASC
                """,
                instance_name,
                since,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Wait-category history query failed: {e}") from e
    return [
        {"captured_at": row["captured_at"].isoformat(), "category": row["category"], "seconds": row["seconds"]}
        for row in rows
    ]


async def prune_old_wait_category_snapshots(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM wait_category_snapshot WHERE captured_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Wait-category prune failed: {e}") from e
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def insert_blocking_event(
    instance_name: str, root_sql: Optional[str], lock_type: Optional[str], blocked_count: int, duration_seconds: float
) -> None:
    try:
        async with await _acquire() as conn:
            await conn.execute(
                """
                INSERT INTO blocking_event
                    (instance_name, root_sql, lock_type, blocked_count, duration_seconds)
                VALUES ($1, $2, $3, $4, $5)
                """,
                instance_name,
                root_sql,
                lock_type,
                blocked_count,
                duration_seconds,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Blocking-event insert failed: {e}") from e


async def insert_activity_sample(instance_name: str, rows: List[Dict[str, Any]]) -> None:
    """Bulk-append one row per currently-active session this cycle — see
    app/modules/monitoring/collector.py's _collect_activity_sample for how rows are built from
    diagnostics.active_sessions(). The single append-only log backing the
    Programs/Databases/Machines/DB Users/Plans/SQL Statements Top-10 history
    and the query drill-down for every other dimension."""
    if not rows:
        return
    captured_at = datetime.now(timezone.utc)
    values = [
        (
            captured_at,
            instance_name,
            r.get("session_id"),
            r.get("database_name"),
            r.get("program_name"),
            r.get("host_name"),
            r.get("login_name"),
            r.get("wait_type"),
            r.get("wait_category"),
            r.get("wait_time_ms") or 0.0,
            r.get("elapsed_time_ms") or 0.0,
            r.get("plan_handle"),
            r.get("query_hash"),
            r.get("sql_text"),
        )
        for r in rows
    ]
    try:
        async with await _acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO activity_sample
                    (captured_at, instance_name, session_id, database_name, program_name, host_name,
                     login_name, wait_type, wait_category, wait_time_ms, elapsed_time_ms, plan_handle,
                     query_hash, sql_text)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                """,
                values,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Activity-sample insert failed: {e}") from e


async def prune_old_activity_samples(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM activity_sample WHERE captured_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Activity-sample prune failed: {e}") from e
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def insert_file_io_snapshot(instance_name: str, deltas: List[Dict[str, Any]]) -> None:
    """Same delta-of-cumulative-counter pattern as insert_wait_category_snapshot
    — deltas is this cycle's per-file IO-stall/bytes/count delta, already
    computed by the caller (app/modules/monitoring/collector.py's _collect_file_io)."""
    if not deltas:
        return
    captured_at = datetime.now(timezone.utc)
    values = [
        (
            captured_at,
            instance_name,
            d["database_name"],
            d["file_name"],
            d.get("drive"),
            d["io_stall_ms"],
            d.get("io_bytes") or 0.0,
            d.get("io_count") or 0.0,
        )
        for d in deltas
    ]
    try:
        async with await _acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO file_io_snapshot
                    (captured_at, instance_name, database_name, file_name, drive, io_stall_ms, io_bytes, io_count)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                values,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"File-IO snapshot insert failed: {e}") from e


async def get_latest_drive_io(instance_name: str, within_seconds: int = 180) -> Dict[str, Dict[str, float]]:
    """Per-drive IO rate + average latency from the most recent file_io_snapshot
    cycle(s) within the window — reads the collector's own recent delta rows
    (Postgres) rather than issuing another live SQL Server query, so the
    fleet Cards' Disk & IO section doesn't add extra per-poll DMV cost on top
    of the health rollup. within_seconds should comfortably exceed one
    collector interval so a slightly-late cycle still shows a value."""
    since = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
    try:
        async with await _acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT drive,
                       SUM(io_bytes) AS total_bytes,
                       SUM(io_stall_ms) AS total_stall_ms,
                       SUM(io_count) AS total_count,
                       MIN(captured_at) AS earliest,
                       MAX(captured_at) AS latest
                FROM file_io_snapshot
                WHERE instance_name = $1 AND captured_at >= $2 AND drive IS NOT NULL
                GROUP BY drive
                """,
                instance_name,
                since,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Drive-IO query failed: {e}") from e

    result: Dict[str, Dict[str, float]] = {}
    for row in rows:
        # Each row is a delta covering the interval *before* its captured_at, so
        # N cycles from earliest..latest cover (latest - earliest) + one interval.
        span_seconds = max(
            (row["latest"] - row["earliest"]).total_seconds() + settings.COLLECTOR_INTERVAL_SECONDS, 1.0
        )
        count = row["total_count"] or 0.0
        result[row["drive"]] = {
            "io_bytes_per_sec": (row["total_bytes"] or 0.0) / span_seconds,
            "latency_ms": (row["total_stall_ms"] / count) if count else 0.0,
        }
    return result


async def insert_category_snapshot(instance_name: str, category: str, severity: str, metric_value: Optional[float]) -> None:
    """A single-category metric_snapshot row with a real, caller-computed
    severity — for signals like 'errors' that (unlike the 8 fleet_health_score
    categories) are only meaningful as a delta over time, so they're written
    by app/modules/monitoring/collector.py's periodic jobs rather than assembled inside
    diagnostics.fleet_health_score's own live-query rollup."""
    captured_at = datetime.now(timezone.utc)
    try:
        async with await _acquire() as conn:
            await conn.execute(
                """
                INSERT INTO metric_snapshot
                    (captured_at, instance_name, overall_severity, category, severity, metric_value)
                VALUES ($1, $2, $3, $4, $3, $5)
                """,
                captured_at,
                instance_name,
                severity,
                category,
                metric_value,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Category snapshot insert failed: {e}") from e


async def get_latest_category_severity(
    instance_name: str, category: str, max_age_seconds: Optional[int] = None
) -> Optional[str]:
    """Latest severity for a category. With max_age_seconds, a reading older
    than that is treated as unknown (None) so a stale CRITICAL can't persist
    after the collector stops writing (instance down, counter reset, etc.)."""
    if max_age_seconds is None:
        max_age_seconds = max(5 * settings.COLLECTOR_INTERVAL_SECONDS, 300)
    since = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    try:
        async with await _acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT severity FROM metric_snapshot
                WHERE instance_name = $1 AND category = $2 AND captured_at >= $3
                ORDER BY captured_at DESC LIMIT 1
                """,
                instance_name,
                category,
                since,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Category severity query failed: {e}") from e
    return row["severity"] if row is not None else None


async def prune_old_file_io_snapshots(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM file_io_snapshot WHERE captured_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"File-IO snapshot prune failed: {e}") from e
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def insert_deadlock_events(instance_name: str, events: List[Dict[str, Any]]) -> None:
    """Durable copy of whatever new (not-already-persisted) deadlock graphs
    app/modules/monitoring/collector.py's _collect_deadlocks found in the system_health ring
    buffer this cycle. ON CONFLICT DO NOTHING is a belt-and-suspenders dedup
    on top of the collector's own in-memory last-seen marker, in case that
    marker is lost to a backend restart mid-buffer."""
    if not events:
        return
    captured_at = datetime.now(timezone.utc)
    values = []
    for e in events:
        occurred_at_raw = e.get("occurred_at")
        if not occurred_at_raw:
            continue
        occurred_at = datetime.fromisoformat(occurred_at_raw.replace("Z", "+00:00"))
        values.append(
            (
                occurred_at,
                captured_at,
                instance_name,
                e.get("database_name"),
                e.get("victim_login"),
                e.get("victim_host"),
                e.get("victim_program"),
                e.get("resource_description"),
                e.get("process_count") or 0,
                e.get("summary"),
            )
        )
    if not values:
        return
    try:
        async with await _acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO deadlock_event
                    (occurred_at, captured_at, instance_name, database_name, victim_login,
                     victim_host, victim_program, resource_description, process_count, summary)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (instance_name, occurred_at) DO NOTHING
                """,
                values,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Deadlock-event insert failed: {e}") from e


async def prune_old_deadlock_events(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM deadlock_event WHERE occurred_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Deadlock-event prune failed: {e}") from e
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


_DIMENSIONS: Dict[str, Dict[str, Any]] = {
    "waits":               {"table": "wait_category_snapshot", "key": "category",     "value": "seconds",         "ms": False},
    "programs":            {"table": "activity_sample",        "key": "program_name", "value": "wait_time_ms",    "ms": True},
    "databases":           {"table": "activity_sample",        "key": "database_name","value": "wait_time_ms",    "ms": True},
    "machines":            {"table": "activity_sample",        "key": "host_name",    "value": "wait_time_ms",    "ms": True},
    "db_users":            {"table": "activity_sample",        "key": "login_name",   "value": "wait_time_ms",    "ms": True},
    "plans":               {"table": "activity_sample",        "key": "plan_handle",  "value": "wait_time_ms",    "ms": True},
    "sql_statements":      {"table": "activity_sample",        "key": "query_hash",   "value": "wait_time_ms",    "ms": True},
    "files":               {"table": "file_io_snapshot",       "key": "file_name",    "value": "io_stall_ms",     "ms": True},
    "drives":              {"table": "file_io_snapshot",       "key": "drive",        "value": "io_stall_ms",     "ms": True},
    "blocking_statements": {"table": "blocking_event",         "key": "root_sql",     "value": "duration_seconds","ms": False},
}


DIMENSION_NAMES = frozenset(_DIMENSIONS) | {"deadlocks"}


_LABEL_LOOKUP = {
    "plans": ("activity_sample", "plan_handle", "sql_text"),
    "sql_statements": ("activity_sample", "query_hash", "sql_text"),
}


async def get_top_dimension_history(instance_name: str, dimension: str, since_days: int, limit: int = 10) -> Dict[str, Any]:
    """Day-bucketed Top-N series (+ an 'Other' rollup for everything outside
    the top N keys) for one of the whitelisted dimensions above."""
    since = datetime.now(timezone.utc) - timedelta(days=since_days)

    try:
        async with await _acquire() as conn:
            if dimension == "deadlocks":
                rows = await conn.fetch(
                    """
                    SELECT date_trunc('day', occurred_at) AS day, COUNT(*) AS value
                    FROM deadlock_event
                    WHERE instance_name = $1 AND occurred_at >= $2
                    GROUP BY day ORDER BY day ASC
                    """,
                    instance_name,
                    since,
                )
                points = [{"day": r["day"].date().isoformat(), "value": r["value"]} for r in rows]
                return {"series": [{"key": "deadlocks", "label": "Deadlocks", "points": points}], "other": []}

            spec = _DIMENSIONS[dimension]
            table, key_col, value_col = spec["table"], spec["key"], spec["value"]
            value_expr = f"{value_col} / 1000.0" if spec["ms"] else value_col

            top_rows = await conn.fetch(
                f"""
                SELECT {key_col} AS key, SUM({value_expr}) AS total
                FROM {table}
                WHERE instance_name = $1 AND captured_at >= $2 AND {key_col} IS NOT NULL
                GROUP BY {key_col}
                ORDER BY total DESC
                LIMIT $3
                """,
                instance_name,
                since,
                limit,
            )
            top_keys = [r["key"] for r in top_rows]

            labels: Dict[str, str] = {k: k for k in top_keys}
            if dimension in _LABEL_LOOKUP and top_keys:
                label_table, label_key_col, label_col = _LABEL_LOOKUP[dimension]
                label_rows = await conn.fetch(
                    f"""
                    SELECT DISTINCT ON ({label_key_col}) {label_key_col} AS key, {label_col} AS label
                    FROM {label_table}
                    WHERE instance_name = $1 AND {label_key_col} = ANY($2::text[])
                    ORDER BY {label_key_col}, captured_at DESC
                    """,
                    instance_name,
                    top_keys,
                )
                for r in label_rows:
                    if r["label"]:
                        labels[r["key"]] = r["label"][:120]

            day_rows = await conn.fetch(
                f"""
                SELECT
                    date_trunc('day', captured_at) AS day,
                    CASE WHEN {key_col} = ANY($3::text[]) THEN {key_col} ELSE NULL END AS bucket_key,
                    SUM({value_expr}) AS value
                FROM {table}
                WHERE instance_name = $1 AND captured_at >= $2
                GROUP BY day, bucket_key
                ORDER BY day ASC
                """,
                instance_name,
                since,
                top_keys,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Dimension history query failed ({dimension}): {e}") from e

    series_points: Dict[str, List[Dict[str, Any]]] = {k: [] for k in top_keys}
    other_points: List[Dict[str, Any]] = []
    for row in day_rows:
        day_iso = row["day"].date().isoformat()
        if row["bucket_key"] is None:
            other_points.append({"day": day_iso, "value": row["value"]})
        else:
            series_points[row["bucket_key"]].append({"day": day_iso, "value": row["value"]})

    series = [{"key": key, "label": labels.get(key, key), "points": series_points[key]} for key in top_keys]
    return {"series": series, "other": other_points}


_ACTIVITY_LOG_COLUMNS = (
    "captured_at, database_name, program_name, host_name, login_name, wait_type, "
    "wait_category, wait_time_ms, elapsed_time_ms, plan_handle, sql_text"
)


_ACTIVITY_DIMENSIONS = {"waits", "programs", "databases", "machines", "db_users", "plans", "sql_statements"}


async def get_dimension_log(instance_name: str, dimension: str, day: str) -> List[Dict[str, Any]]:
    """Raw rows for the Specific-Day drill-down — reads whichever table
    get_top_dimension_history reads from for that dimension, filtered to one
    calendar day, no aggregation. For dimension='waits' specifically, this
    reads activity_sample (not wait_category_snapshot, which carries no query
    text) — the direct answer to 'wait_type is high, show me the queries'."""
    day_start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    if dimension in _ACTIVITY_DIMENSIONS:
        table, time_col, columns = "activity_sample", "captured_at", _ACTIVITY_LOG_COLUMNS
    elif dimension in ("files", "drives"):
        table, time_col, columns = "file_io_snapshot", "captured_at", "captured_at, database_name, file_name, drive, io_stall_ms"
    elif dimension == "blocking_statements":
        table, time_col, columns = "blocking_event", "captured_at", "captured_at, root_sql, lock_type, blocked_count, duration_seconds"
    elif dimension == "deadlocks":
        table, time_col, columns = (
            "deadlock_event",
            "occurred_at",
            "occurred_at, database_name, victim_login, victim_host, victim_program, resource_description, process_count, summary",
        )
    else:
        raise ValueError(f"Unknown dimension: {dimension}")

    try:
        async with await _acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {columns}
                FROM {table}
                WHERE instance_name = $1 AND {time_col} >= $2 AND {time_col} < $3
                ORDER BY {time_col} DESC
                LIMIT 500
                """,
                instance_name,
                day_start,
                day_end,
            )
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Dimension log query failed ({dimension}): {e}") from e

    result = []
    for row in rows:
        item = dict(row)
        for key in ("captured_at", "occurred_at"):
            if item.get(key) is not None:
                item[key] = item[key].isoformat()
        result.append(item)
    return result


async def prune_old_blocking_events(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with await _acquire() as conn:
            result = await conn.execute("DELETE FROM blocking_event WHERE captured_at < $1", cutoff)
    except RepositoryUnavailable:
        raise
    except Exception as e:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable(f"Blocking-event prune failed: {e}") from e
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
