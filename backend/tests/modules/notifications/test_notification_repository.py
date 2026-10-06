"""Real database checks opt in to a dedicated disposable PostgreSQL database."""

import app.infrastructure.postgres.pool as postgres_pool
import app.infrastructure.postgres.schema as postgres_schema
import app.modules.notifications.repository as notifications_repository
import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import pytest_asyncio

from app.core.config import settings
from app.modules.notifications.dispatcher import plan
from app.modules.notifications.models import DeliveryResult
from app.modules.notifications.models import RuleInput


@pytest_asyncio.fixture
async def database(monkeypatch):
    dsn = os.environ.get("NOTIFICATION_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set NOTIFICATION_TEST_POSTGRES_DSN to a disposable test database")
    assert urlsplit(dsn).path == "/data_eyes_notification_test", "Refusing a non-test database"
    monkeypatch.setattr(settings, "REPOSITORY_DSN", dsn)
    monkeypatch.setattr(postgres_pool, "_pool", None)
    pool = await postgres_pool.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS metric_snapshot (captured_at timestamptz, instance_name text, category text, severity text, metric_value double precision)")
    for _ in range(2):
        await postgres_schema.ensure_notification_schema()
        await postgres_schema.ensure_alert_schema()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE notification_log, notification_rule, notification_channel, notification_state, metric_snapshot, "
                           "alert_state, alert_event RESTART IDENTITY CASCADE")
    yield pool
    await postgres_pool.close_pool()


@pytest.mark.asyncio
async def test_migration_crud_atomic_state_and_claims(database):
    channel = await notifications_repository.save_notification_channel({"name": "ops", "type": "slack", "enabled": True,
                                                         "config": {"webhook_url": "https://hooks.example/secret"}})
    assert channel["config"]["webhook_url"] == "********"
    rule = await notifications_repository.save_notification_rule(RuleInput(name="critical", channel_id=channel["id"], cooldown_seconds=0).model_dump())
    assert rule["severities"] == ["CRITICAL"]
    now = datetime.now(timezone.utc)
    async with database.acquire() as conn:
        await conn.execute("INSERT INTO metric_snapshot VALUES($1,'prod','alert.full_backup_age','OK',0)", now - timedelta(minutes=1))
    await notifications_repository.enqueue_notifications(plan, now - timedelta(minutes=2))
    assert await notifications_repository.list_notification_logs() == []
    async with database.acquire() as conn:
        await conn.execute("INSERT INTO metric_snapshot VALUES($1,'prod','alert.full_backup_age','CRITICAL',3)", now)
    await asyncio.gather(*(notifications_repository.enqueue_notifications(plan, now - timedelta(minutes=2)) for _ in range(4)))
    logs = await notifications_repository.list_notification_logs()
    assert len(logs) == 1 and logs[0]["status"] == "pending"
    claimed = await asyncio.gather(*(notifications_repository.claim_notification() for _ in range(4)))
    row = next(r for r in claimed if r)
    assert sum(r is not None for r in claimed) == 1
    assert not await notifications_repository.delete_notification("logs", row["id"])
    await notifications_repository.finish_notification(row, DeliveryResult(ok=False, message="Provider HTTP 503", retryable=True, retry_after=120))
    assert await notifications_repository.claim_notification() is None
    async with database.acquire() as conn:
        await conn.execute("UPDATE notification_log SET next_attempt_at=now()-interval '1 second'")
    row = await notifications_repository.claim_notification()
    assert row["attempts"] == 2
    await notifications_repository.finish_notification(row, DeliveryResult(ok=True))
    assert (await notifications_repository.list_notification_logs())[0]["status"] == "sent"
    assert await notifications_repository.delete_notification("channels", channel["id"])
    assert await notifications_repository.list_notification_rules() == []
    assert (await notifications_repository.list_notification_logs())[0]["channel_id"] is None
    assert await notifications_repository.delete_notification("logs", row["id"])


@pytest.mark.asyncio
async def test_expired_lease_and_retry_limit(database):
    async with database.acquire() as conn:
        await conn.execute("INSERT INTO notification_log(instance_name,category,event,status,attempts,next_attempt_at) VALUES('prod','backup','{}','sending',2,now()-interval '1 second')")
    row = await notifications_repository.claim_notification()
    assert row["attempts"] == 3
    await notifications_repository.finish_notification(row, DeliveryResult(ok=False, retryable=True, message="Transient failure"))
    assert (await notifications_repository.list_notification_logs())[0]["status"] == "failed"
    assert await notifications_repository.claim_notification() is None


@pytest.mark.asyncio
async def test_planning_failure_rolls_back_state(database):
    now = datetime.now(timezone.utc)
    async with database.acquire() as conn:
        await conn.execute("INSERT INTO metric_snapshot VALUES($1,'prod','alert.full_backup_age','OK',0)", now)
    def failing(*args):
        raise RuntimeError("planning failure")
    with pytest.raises(RuntimeError):
        await notifications_repository.enqueue_notifications(failing, now - timedelta(minutes=1))
    async with database.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM notification_state") == 0


@pytest.mark.asyncio
async def test_fleet_categories_do_not_notify_and_events_dispatch_once(database):
    channel = await notifications_repository.save_notification_channel({"name": "ops", "type": "slack", "enabled": True,
                                                         "config": {"webhook_url": "https://hooks.example/secret"}})
    await notifications_repository.save_notification_rule(
        RuleInput(name="all", channel_id=channel["id"], cooldown_seconds=0, severities=["WARNING", "CRITICAL"]).model_dump())
    now = datetime.now(timezone.utc)
    async with database.acquire() as conn:
        # Dashboard fleet categories share metric_snapshot but are not alerts.
        await conn.execute("INSERT INTO metric_snapshot VALUES($1,'prod','backup_health','OK',0)", now - timedelta(minutes=1))
        await conn.execute("INSERT INTO notification_state VALUES('prod','backup_health','OK',$1)", now - timedelta(minutes=5))
        await conn.execute("INSERT INTO alert_event(instance_name,alert_key,dedup_key,severity,occurred_at,detail) "
                           "VALUES('prod','job_failed','1','CRITICAL',$1,'nightly backup failed')", now)
        await conn.execute("INSERT INTO metric_snapshot VALUES($1,'prod','backup_health','CRITICAL',3)", now)
    await notifications_repository.enqueue_notifications(plan, now - timedelta(minutes=2))
    await notifications_repository.enqueue_notifications(plan, now - timedelta(minutes=2))
    logs = await notifications_repository.list_notification_logs()
    assert [log["category"] for log in logs] == ["job_failed"]
    assert logs[0]["event"]["kind"] == "event" and logs[0]["event"]["detail"] == "nightly backup failed"


def test_fresh_and_existing_database_schema_match():
    backend = Path(__file__).resolve().parents[3]
    init = (backend.parent / "repository/init/10-init.sql").read_text(encoding="utf-8")
    for name in ("notification_schema.sql", "alert_schema.sql"):
        assert (backend / "app/infrastructure/postgres" / name).read_text(encoding="utf-8").strip() in init
