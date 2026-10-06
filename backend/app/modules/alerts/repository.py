"""Alert settings, state, events and check memory in the repository database."""

import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import asyncpg

from app.infrastructure.postgres.pool import RepositoryUnavailable
from app.infrastructure.postgres.pool import _acquire
from app.infrastructure.postgres.pool import _invalidate_pool_on_failure


@asynccontextmanager
async def alert_connection():
    try:
        async with await _acquire() as conn:
            yield conn
    except RepositoryUnavailable:
        raise
    except (asyncpg.PostgresError, OSError) as exc:
        _invalidate_pool_on_failure()
        raise RepositoryUnavailable("Alert repository unavailable") from exc


async def list_settings() -> List[Dict[str, Any]]:
    async with alert_connection() as conn:
        rows = await conn.fetch("SELECT * FROM alert_setting ORDER BY alert_key, instance_name")
    return [dict(row) for row in rows]


async def upsert_setting(payload: Dict[str, Any]) -> Dict[str, Any]:
    async with alert_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO alert_setting (alert_key, instance_name, enabled, warning_threshold, critical_threshold,
                                       tier, confirm_samples, excluded_databases, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
            ON CONFLICT (alert_key, instance_name) DO UPDATE SET
                enabled = excluded.enabled, warning_threshold = excluded.warning_threshold,
                critical_threshold = excluded.critical_threshold, tier = excluded.tier,
                confirm_samples = excluded.confirm_samples, excluded_databases = excluded.excluded_databases,
                updated_at = now()
            RETURNING *
            """,
            payload["alert_key"], payload["instance_name"], payload["enabled"], payload["warning_threshold"],
            payload["critical_threshold"], payload["tier"], payload["confirm_samples"], payload["excluded_databases"])
    return dict(row)


async def delete_setting(alert_key: str, instance_name: str) -> bool:
    async with alert_connection() as conn:
        result = await conn.execute(
            "DELETE FROM alert_setting WHERE alert_key = $1 AND instance_name = $2", alert_key, instance_name)
    return result == "DELETE 1"


async def reset_alert(alert_key: str, instance_name: Optional[str]) -> None:
    """Forget an alert's state after it is disabled, so re-enabling starts a
    fresh baseline instead of firing a stale recovery."""
    async with alert_connection() as conn:
        async with conn.transaction():
            for table, column in (("notification_state", "category"), ("alert_state", "alert_key")):
                await conn.execute(
                    f"DELETE FROM {table} WHERE {column} = $1 AND ($2::text IS NULL OR instance_name = $2)",
                    alert_key, instance_name)


async def list_states() -> List[Dict[str, Any]]:
    async with alert_connection() as conn:
        rows = await conn.fetch("SELECT * FROM alert_state ORDER BY instance_name, alert_key")
    return [dict(row) for row in rows]


async def save_state(instance_name: str, alert_key: str, state: Dict[str, Any]) -> None:
    async with alert_connection() as conn:
        await conn.execute(
            """
            INSERT INTO alert_state (instance_name, alert_key, severity, observed_severity, streak, metric_value,
                                     detail, status, status_message, checked_at, changed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (instance_name, alert_key) DO UPDATE SET
                severity = excluded.severity, observed_severity = excluded.observed_severity,
                streak = excluded.streak, metric_value = excluded.metric_value, detail = excluded.detail,
                status = excluded.status, status_message = excluded.status_message,
                checked_at = excluded.checked_at, changed_at = excluded.changed_at
            """,
            instance_name, alert_key, state["severity"], state["observed_severity"], state["streak"],
            state["metric_value"], state["detail"], state["status"], state["status_message"],
            state["checked_at"], state["changed_at"])


async def load_memory(instance_name: str) -> Dict[str, Dict[str, Any]]:
    async with alert_connection() as conn:
        rows = await conn.fetch("SELECT alert_key, memory FROM alert_memory WHERE instance_name = $1", instance_name)
    return {row["alert_key"]: json.loads(row["memory"]) for row in rows}


async def save_memory(instance_name: str, alert_key: str, memory: Dict[str, Any]) -> None:
    async with alert_connection() as conn:
        await conn.execute(
            """
            INSERT INTO alert_memory (instance_name, alert_key, memory, updated_at) VALUES ($1, $2, $3::jsonb, now())
            ON CONFLICT (instance_name, alert_key) DO UPDATE SET memory = excluded.memory, updated_at = now()
            """,
            instance_name, alert_key, json.dumps(memory, default=str))


async def insert_events(instance_name: str, alert_key: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Insert occurrences idempotently; returns only the newly stored ones."""
    inserted = []
    if not rows:
        return inserted
    async with alert_connection() as conn:
        async with conn.transaction():
            for row in rows:
                stored = await conn.fetchrow(
                    """
                    INSERT INTO alert_event (instance_name, alert_key, dedup_key, severity, occurred_at, metric_value, detail)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (instance_name, alert_key, dedup_key) DO NOTHING
                    RETURNING alert_event_id, severity, detail
                    """,
                    instance_name, alert_key, row["dedup_key"], row["severity"], row["occurred_at"],
                    row["metric_value"], row["detail"])
                if stored:
                    inserted.append(dict(stored))
    return inserted


async def list_events(limit: int = 100, instance_name: Optional[str] = None) -> List[Dict[str, Any]]:
    async with alert_connection() as conn:
        rows = await conn.fetch(
            "SELECT alert_event_id, instance_name, alert_key, severity, occurred_at, captured_at, metric_value, detail "
            "FROM alert_event WHERE ($2::text IS NULL OR instance_name = $2) ORDER BY alert_event_id DESC LIMIT $1",
            limit, instance_name)
    return [dict(row) for row in rows]


async def prune_old_events(retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    async with alert_connection() as conn:
        result = await conn.execute("DELETE FROM alert_event WHERE captured_at < $1 AND dispatched", cutoff)
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def deadlocks_after(instance_name: str, last_event_id: int) -> List[Dict[str, Any]]:
    async with alert_connection() as conn:
        rows = await conn.fetch(
            "SELECT event_id, occurred_at, database_name, victim_login, victim_host, victim_program, process_count "
            "FROM deadlock_event WHERE instance_name = $1 AND event_id > $2 ORDER BY event_id LIMIT 100",
            instance_name, last_event_id)
    return [dict(row) for row in rows]


async def max_deadlock_id(instance_name: str) -> int:
    async with alert_connection() as conn:
        value = await conn.fetchval("SELECT max(event_id) FROM deadlock_event WHERE instance_name = $1", instance_name)
    return int(value or 0)


async def channel_failures(since: datetime) -> List[Dict[str, Any]]:
    """Failed alert deliveries per channel; channel test sends are excluded."""
    async with alert_connection() as conn:
        rows = await conn.fetch(
            "SELECT c.name, count(*) AS failed FROM notification_log l JOIN notification_channel c ON c.id = l.channel_id "
            "WHERE l.status = 'failed' AND l.created_at >= $1 AND l.category <> 'Notification test' GROUP BY c.name",
            since)
    return [dict(row) for row in rows]


async def channel_ids() -> List[int]:
    async with alert_connection() as conn:
        return [row["id"] for row in await conn.fetch("SELECT id FROM notification_channel")]


async def get_digest_setting() -> Dict[str, Any]:
    async with alert_connection() as conn:
        row = await conn.fetchrow("SELECT enabled, hour_utc, channel_ids, last_sent_on FROM alert_digest_setting WHERE alert_digest_setting_id = 1")
    if row is None:
        return {"enabled": False, "hour_utc": 7, "channel_ids": [], "last_sent_on": None}
    return {**dict(row), "channel_ids": list(row["channel_ids"])}


async def save_digest_setting(enabled: bool, hour_utc: int, channel_ids: List[int]) -> Dict[str, Any]:
    async with alert_connection() as conn:
        await conn.execute(
            "INSERT INTO alert_digest_setting (alert_digest_setting_id, enabled, hour_utc, channel_ids) VALUES (1, $1, $2, $3) "
            "ON CONFLICT (alert_digest_setting_id) DO UPDATE SET enabled = $1, hour_utc = $2, channel_ids = $3",
            enabled, hour_utc, channel_ids)
    return await get_digest_setting()


async def claim_digest(today: date) -> bool:
    """Atomically mark today's checklist as sent so concurrent workers send it once."""
    async with alert_connection() as conn:
        claimed = await conn.fetchval(
            "UPDATE alert_digest_setting SET last_sent_on = $1 WHERE alert_digest_setting_id = 1 "
            "AND last_sent_on IS DISTINCT FROM $1 RETURNING 1", today)
    return bool(claimed)


async def recent_event_counts(since: datetime) -> List[Dict[str, Any]]:
    async with alert_connection() as conn:
        rows = await conn.fetch(
            "SELECT instance_name, alert_key, severity, count(*) AS events FROM alert_event WHERE captured_at >= $1 "
            "GROUP BY instance_name, alert_key, severity", since)
    return [dict(row) for row in rows]


async def enqueue_digest(channel_ids: List[int], event_json: str, instance_name: str, category: str) -> int:
    async with alert_connection() as conn:
        result = await conn.execute(
            "INSERT INTO notification_log (channel_id, rule_id, instance_name, category, event, status) "
            "SELECT id, NULL, $2, $3, $4::jsonb, 'pending' FROM notification_channel WHERE enabled AND id = ANY($1)",
            channel_ids, instance_name, category, event_json)
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
