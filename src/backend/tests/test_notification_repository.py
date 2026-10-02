"""Real database checks opt in to a dedicated disposable PostgreSQL database."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import pytest_asyncio

from app import repository
from app.config import settings
from app.notifications.dispatcher import plan
from app.notifications.models import DeliveryResult, RuleInput


@pytest_asyncio.fixture
async def database(monkeypatch):
    dsn = os.environ.get("NOTIFICATION_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set NOTIFICATION_TEST_POSTGRES_DSN to a disposable test database")
    assert urlsplit(dsn).path == "/data_eyes_notification_test", "Refusing a non-test database"
    monkeypatch.setattr(settings, "REPOSITORY_DSN", dsn)
    monkeypatch.setattr(repository, "_pool", None)
    pool = await repository.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS metric_snapshot (captured_at timestamptz, instance_name text, category text, severity text, metric_value double precision)")
    await repository.ensure_notification_schema()
    await repository.ensure_notification_schema()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE notification_log, notification_rule, notification_channel, notification_state, metric_snapshot RESTART IDENTITY CASCADE")
    yield pool
    await repository.close_pool()


@pytest.mark.asyncio
async def test_migration_crud_atomic_state_and_claims(database):
    channel = await repository.save_notification_channel({"name": "ops", "type": "slack", "enabled": True,
                                                         "config": {"webhook_url": "https://hooks.example/secret"}})
    assert channel["config"]["webhook_url"] == "********"
    rule = await repository.save_notification_rule(RuleInput(name="critical", channel_id=channel["id"], cooldown_seconds=0).model_dump())
    assert rule["severities"] == ["CRITICAL"]
    now = datetime.now(timezone.utc)
    async with database.acquire() as conn:
        await conn.execute("INSERT INTO metric_snapshot VALUES($1,'prod','backup','OK',0)", now - timedelta(minutes=1))
    await repository.enqueue_notifications(plan, now - timedelta(minutes=2))
    assert await repository.list_notification_logs() == []
    async with database.acquire() as conn:
        await conn.execute("INSERT INTO metric_snapshot VALUES($1,'prod','backup','CRITICAL',3)", now)
    await asyncio.gather(*(repository.enqueue_notifications(plan, now - timedelta(minutes=2)) for _ in range(4)))
    logs = await repository.list_notification_logs()
    assert len(logs) == 1 and logs[0]["status"] == "pending"
    claimed = await asyncio.gather(*(repository.claim_notification() for _ in range(4)))
    row = next(r for r in claimed if r)
    assert sum(r is not None for r in claimed) == 1
    assert not await repository.delete_notification("logs", row["id"])
    await repository.finish_notification(row, DeliveryResult(ok=False, message="Provider HTTP 503", retryable=True, retry_after=120))
    assert await repository.claim_notification() is None
    async with database.acquire() as conn:
        await conn.execute("UPDATE notification_log SET next_attempt_at=now()-interval '1 second'")
    row = await repository.claim_notification()
    assert row["attempts"] == 2
    await repository.finish_notification(row, DeliveryResult(ok=True))
    assert (await repository.list_notification_logs())[0]["status"] == "sent"
    assert await repository.delete_notification("channels", channel["id"])
    assert await repository.list_notification_rules() == []
    assert (await repository.list_notification_logs())[0]["channel_id"] is None
    assert await repository.delete_notification("logs", row["id"])


@pytest.mark.asyncio
async def test_expired_lease_and_retry_limit(database):
    async with database.acquire() as conn:
        await conn.execute("INSERT INTO notification_log(instance_name,category,event,status,attempts,next_attempt_at) VALUES('prod','backup','{}','sending',2,now()-interval '1 second')")
    row = await repository.claim_notification()
    assert row["attempts"] == 3
    await repository.finish_notification(row, DeliveryResult(ok=False, retryable=True, message="Transient failure"))
    assert (await repository.list_notification_logs())[0]["status"] == "failed"
    assert await repository.claim_notification() is None


@pytest.mark.asyncio
async def test_planning_failure_rolls_back_state(database):
    now = datetime.now(timezone.utc)
    async with database.acquire() as conn:
        await conn.execute("INSERT INTO metric_snapshot VALUES($1,'prod','backup','OK',0)", now)
    def failing(*args):
        raise RuntimeError("planning failure")
    with pytest.raises(RuntimeError):
        await repository.enqueue_notifications(failing, now - timedelta(minutes=1))
    async with database.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM notification_state") == 0


def test_fresh_and_existing_database_schema_match():
    backend = Path(__file__).resolve().parents[1]
    schema = (backend / "app/notification_schema.sql").read_text(encoding="utf-8").strip()
    assert schema in (backend.parent / "repository/init.sql").read_text(encoding="utf-8")
