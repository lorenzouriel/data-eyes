"""Real database checks opt in to a dedicated disposable PostgreSQL database."""

import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

import pytest
import pytest_asyncio

import app.infrastructure.postgres.pool as postgres_pool
import app.infrastructure.postgres.schema as postgres_schema
import app.modules.alerts.repository as alerts_repository
from app.core.config import settings

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


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
        await conn.execute("CREATE TABLE IF NOT EXISTS deadlock_event (event_id bigserial PRIMARY KEY, occurred_at timestamptz, "
                           "instance_name text, database_name text, victim_login text, victim_host text, victim_program text, "
                           "process_count int)")
    await postgres_schema.ensure_notification_schema()
    await postgres_schema.ensure_alert_schema()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE alert_setting, alert_state, alert_event, alert_memory, notification_state, notification_log, "
                           "notification_channel, deadlock_event RESTART IDENTITY CASCADE")
        await conn.execute("UPDATE alert_digest_setting SET enabled = false, channel_ids = '{}', last_sent_on = NULL")
    yield pool
    await postgres_pool.close_pool()


def setting(**values):
    return {"alert_key": "disk_space", "instance_name": "", "enabled": None, "warning_threshold": None,
            "critical_threshold": None, "tier": None, "confirm_samples": None, "excluded_databases": None, **values}


def state(severity):
    return {"severity": severity, "observed_severity": severity, "streak": 1, "metric_value": 3.0, "detail": "E:\\ 3 GB",
            "status": "ok", "status_message": "", "checked_at": NOW, "changed_at": NOW}


@pytest.mark.asyncio
async def test_settings_state_and_reset(database):
    await alerts_repository.upsert_setting(setting(enabled=False, excluded_databases=["Dev"]))
    saved = await alerts_repository.upsert_setting(setting(enabled=True, warning_threshold=50.0))
    assert saved["enabled"] and saved["excluded_databases"] is None
    await alerts_repository.upsert_setting(setting(instance_name="prod", tier="fast"))
    assert [(r["instance_name"], r["tier"]) for r in await alerts_repository.list_settings()] == [("", None), ("prod", "fast")]
    assert await alerts_repository.delete_setting("disk_space", "prod")
    assert not await alerts_repository.delete_setting("disk_space", "prod")

    await alerts_repository.save_state("prod", "disk_space", state("WARNING"))
    await alerts_repository.save_state("prod", "disk_space", state("CRITICAL"))
    await alerts_repository.save_state("dev", "disk_space", state("OK"))
    async with database.acquire() as conn:
        await conn.execute("INSERT INTO notification_state VALUES ('prod','disk_space','CRITICAL',$1,$1)", NOW)
    assert {(s["instance_name"], s["severity"]) for s in await alerts_repository.list_states()} == {("prod", "CRITICAL"), ("dev", "OK")}
    await alerts_repository.reset_alert("disk_space", "prod")
    assert [s["instance_name"] for s in await alerts_repository.list_states()] == ["dev"]
    async with database.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM notification_state") == 0


@pytest.mark.asyncio
async def test_events_are_idempotent_and_memory_round_trips(database):
    row = {"dedup_key": "42", "severity": "CRITICAL", "occurred_at": NOW, "metric_value": None, "detail": "Nightly backup"}
    results = await asyncio.gather(*(alerts_repository.insert_events("prod", "job_failed", [row]) for _ in range(3)))
    assert sum(len(r) for r in results) == 1
    assert [e["detail"] for e in await alerts_repository.list_events(10, "prod")] == ["Nightly backup"]
    assert await alerts_repository.list_events(10, "other") == []
    assert await alerts_repository.prune_old_events(0) == 0  # undispatched events are never pruned

    await alerts_repository.save_memory("prod", "job_failed", {"last_instance_id": 7, "seen": ["a"]})
    await alerts_repository.save_memory("prod", "job_failed", {"last_instance_id": 9})
    assert await alerts_repository.load_memory("prod") == {"job_failed": {"last_instance_id": 9}}


@pytest.mark.asyncio
async def test_deadlocks_channel_failures_and_digest(database):
    async with database.acquire() as conn:
        await conn.execute("INSERT INTO deadlock_event (occurred_at, instance_name, database_name, process_count) "
                           "VALUES ($1,'prod','Sales',2), ($1,'prod','Sales',3), ($1,'dev','Dev',2)", NOW)
        channel = await conn.fetchval("INSERT INTO notification_channel (name, type, config) VALUES ('ops','slack','x') RETURNING id")
        await conn.execute("INSERT INTO notification_log (channel_id, instance_name, category, event, status) VALUES "
                           "($1,'prod','disk_space','{}','failed'), ($1,'prod','Notification test','{}','failed'), "
                           "($1,'prod','disk_space','{}','sent')", channel)
    assert await alerts_repository.max_deadlock_id("prod") == 2
    assert [d["process_count"] for d in await alerts_repository.deadlocks_after("prod", 1)] == [3]
    assert await alerts_repository.channel_failures(datetime.now(timezone.utc) - timedelta(hours=1)) == [{"name": "ops", "failed": 1}]

    await alerts_repository.save_digest_setting(True, 6, [channel])
    claims = await asyncio.gather(*(alerts_repository.claim_digest(date(2026, 10, 5)) for _ in range(4)))
    assert claims.count(True) == 1
    assert (await alerts_repository.get_digest_setting())["last_sent_on"] == date(2026, 10, 5)
    assert await alerts_repository.enqueue_digest([channel, 999], '{"kind": "digest"}', "Fleet", "daily_checklist") == 1
