"""Repository implementation."""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import asyncpg
from app.core import crypto
from app.infrastructure.postgres.pool import RepositoryUnavailable
from app.infrastructure.postgres.pool import _acquire


@asynccontextmanager
async def notification_connection():
    """Normalize DB failures without leaking encrypted channel configuration."""
    try:
        async with await _acquire() as conn:
            yield conn
    except (asyncpg.PostgresError, OSError, RepositoryUnavailable) as exc:
        raise RepositoryUnavailable("Notification repository unavailable") from exc


def _notification_channel(row, decrypt=False):
    if row is None:
        return None
    from app.modules.notifications.models import SECRET_FIELDS
    from app.modules.notifications.models import MASK
    result = dict(row)
    config = json.loads(crypto.decrypt(result["config"]))
    result["config"] = config if decrypt else {
        key: MASK if key in SECRET_FIELDS and value else value for key, value in config.items()
    }
    return result


async def list_notification_channels():
    async with notification_connection() as conn:
        rows = await conn.fetch("SELECT * FROM notification_channel ORDER BY id")
    return [_notification_channel(row) for row in rows]


async def get_notification_channel(channel_id, *, decrypt=False):
    async with notification_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM notification_channel WHERE id=$1", channel_id)
    return _notification_channel(row, decrypt)


async def save_notification_channel(payload, channel_id=None):
    encrypted = crypto.encrypt(json.dumps(payload["config"]))
    async with notification_connection() as conn:
        if channel_id is None:
            row = await conn.fetchrow(
                "INSERT INTO notification_channel(name,type,enabled,config) VALUES($1,$2,$3,$4) RETURNING *",
                payload["name"], payload["type"], payload["enabled"], encrypted)
        else:
            row = await conn.fetchrow(
                "UPDATE notification_channel SET name=$1,type=$2,enabled=$3,config=$4 WHERE id=$5 RETURNING *",
                payload["name"], payload["type"], payload["enabled"], encrypted, channel_id)
    return _notification_channel(row)


def _notification_rule(row):
    if row is None:
        return None
    result = dict(row)
    return {**json.loads(result.pop("definition")), **result}


async def list_notification_rules():
    async with notification_connection() as conn:
        rows = await conn.fetch("SELECT * FROM notification_rule ORDER BY id")
    return [_notification_rule(row) for row in rows]


async def save_notification_rule(payload, rule_id=None):
    async with notification_connection() as conn:
        if rule_id is None:
            row = await conn.fetchrow(
                "INSERT INTO notification_rule(channel_id,name,enabled,definition) VALUES($1,$2,$3,$4::jsonb) RETURNING *",
                payload["channel_id"], payload["name"], payload["enabled"], json.dumps(payload))
        else:
            row = await conn.fetchrow(
                "UPDATE notification_rule SET channel_id=$1,name=$2,enabled=$3,definition=$4::jsonb WHERE id=$5 RETURNING *",
                payload["channel_id"], payload["name"], payload["enabled"], json.dumps(payload), rule_id)
    return _notification_rule(row)


async def delete_notification(kind, row_id):
    table = {"channels": "notification_channel", "rules": "notification_rule", "logs": "notification_log"}[kind]
    async with notification_connection() as conn:
        # Delivery records are immutable while queued or in flight.
        suffix = " AND status NOT IN ('pending','sending')" if kind == "logs" else ""
        result = await conn.execute(f"DELETE FROM {table} WHERE id=$1{suffix}", row_id)
    return result == "DELETE 1"


async def list_notification_logs(limit=100, offset=0, channel_id=None):
    async with notification_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM notification_log WHERE ($3::bigint IS NULL OR channel_id=$3) "
            "ORDER BY id DESC LIMIT $1 OFFSET $2", limit, offset, channel_id)
    return [{**dict(row), "event": json.loads(row["event"])} for row in rows]


async def enqueue_notifications(planner, since):
    """Atomically persist transitions and their outbox records across workers.

    Only the alert catalog notifies: state alerts arrive as `alert.<key>`
    rows in metric_snapshot (the dashboard's own fleet categories in that
    table are not alerts), and event alerts as undispatched alert_event rows."""
    from app.modules.alerts.catalog import CATALOG_BY_KEY
    from app.modules.alerts.catalog import SNAPSHOT_PREFIX
    from app.modules.alerts.catalog import title

    now = datetime.now(timezone.utc)
    async with notification_connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(20261003)")
            rows = await conn.fetch(
                "SELECT DISTINCT ON (s.instance_name, s.category) s.instance_name, s.category, s.severity, s.metric_value, "
                "s.captured_at, a.detail FROM metric_snapshot s LEFT JOIN alert_state a "
                "ON a.instance_name = s.instance_name AND $2 || a.alert_key = s.category "
                "WHERE s.captured_at >= $1 AND s.category LIKE $2 || '%' "
                "ORDER BY s.instance_name, s.category, s.captured_at DESC", since, SNAPSHOT_PREFIX)
            snapshots = []
            for row in rows:
                key = row["category"][len(SNAPSHOT_PREFIX):]
                if key in CATALOG_BY_KEY:
                    snapshots.append({**dict(row), "category": key, "title": title(key)})
            event_rows = await conn.fetch(
                "SELECT alert_event_id, instance_name, alert_key, severity, occurred_at, metric_value, detail "
                "FROM alert_event WHERE NOT dispatched ORDER BY alert_event_id LIMIT 500 FOR UPDATE SKIP LOCKED")
            events = [{**dict(row), "category": row["alert_key"], "title": title(row["alert_key"])} for row in event_rows]
            states = await conn.fetch("SELECT * FROM notification_state")
            rules = await conn.fetch(
                "SELECT r.* FROM notification_rule r JOIN notification_channel c ON c.id=r.channel_id "
                "WHERE r.enabled AND c.enabled")
            previous = await conn.fetch(
                "SELECT rule_id,instance_name,category,max(created_at) AS last_sent FROM notification_log "
                "WHERE status != 'suppressed' AND created_at >= $1 GROUP BY rule_id,instance_name,category",
                now - timedelta(days=7))
            planned = planner(snapshots, states, [_notification_rule(r) for r in rules], previous, now, events)
            for snapshot in snapshots:
                await conn.execute(
                    "INSERT INTO notification_state(instance_name,category,severity,captured_at,changed_at) "
                    "VALUES($1,$2,$3,$4,$4) ON CONFLICT(instance_name,category) DO UPDATE SET "
                    "changed_at=CASE WHEN notification_state.severity <> excluded.severity THEN excluded.captured_at "
                    "ELSE COALESCE(notification_state.changed_at, notification_state.captured_at) END, "
                    "severity=excluded.severity,captured_at=excluded.captured_at "
                    "WHERE notification_state.captured_at < excluded.captured_at",
                    snapshot["instance_name"], snapshot["category"], snapshot["severity"], snapshot["captured_at"])
            if event_rows:
                await conn.execute("UPDATE alert_event SET dispatched = TRUE WHERE alert_event_id = ANY($1::bigint[])",
                                   [row["alert_event_id"] for row in event_rows])
            for rule, event, reason in planned:
                await conn.execute(
                    "INSERT INTO notification_log(channel_id,rule_id,instance_name,category,event,status,message,created_at) "
                    "VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,$8)", rule["channel_id"], rule["id"], event.instance,
                    event.category, event.model_dump_json(), "suppressed" if reason else "pending", reason, now)


async def claim_notification():
    async with notification_connection() as conn:
        row = await conn.fetchrow(
            "UPDATE notification_log SET status='sending', attempts=attempts+1, "
            "next_attempt_at=now()+interval '5 minutes' WHERE id=("
            "SELECT id FROM notification_log WHERE status IN ('pending','sending') AND next_attempt_at<=now() "
            "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *")
    return dict(row) if row else None


async def finish_notification(row, result):
    retry = result.retryable and row["attempts"] < 3
    async with notification_connection() as conn:
        await conn.execute(
            "UPDATE notification_log SET status=$2,message=$3,next_attempt_at=$4,delivered_at=$5 "
            "WHERE id=$1 AND status='sending' AND attempts=$6",
            row["id"], "sent" if result.ok else "pending" if retry else "failed", result.message,
            datetime.now(timezone.utc) + timedelta(seconds=max(30, result.retry_after)),
            datetime.now(timezone.utc) if result.ok else None, row["attempts"])


async def log_notification_test(channel_id, event, result):
    async with notification_connection() as conn:
        await conn.execute(
            "INSERT INTO notification_log(channel_id,instance_name,category,event,status,message,attempts,delivered_at) "
            "VALUES($1,$2,$3,$4::jsonb,$5,$6,$7,$8)", channel_id, event.instance, event.category,
            event.model_dump_json(), "sent" if result.ok else "failed", result.message, result.attempts,
            datetime.now(timezone.utc) if result.ok else None)
