from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.modules.alerts.repository as alerts_repository
import app.modules.instances.repository as instances_repository
from app.modules.alerts import digest

NOW = datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc)


def state(instance, key, severity="OK", status="ok", detail=""):
    return {"instance_name": instance, "alert_key": key, "severity": severity, "status": status, "detail": detail}


@pytest.fixture
def fleet(monkeypatch):
    monkeypatch.setattr(instances_repository, "list_instances",
                        AsyncMock(return_value=[SimpleNamespace(name="prod"), SimpleNamespace(name="dev")]))
    monkeypatch.setattr(alerts_repository, "list_states", AsyncMock(return_value=[
        state("prod", "disk_space", "CRITICAL", detail="CRITICAL E:\\: 3 GB\nmore"),
        state("prod", "login_failed", status="error"), state("dev", "disk_space"), state("gone", "disk_space", "CRITICAL")]))
    monkeypatch.setattr(alerts_repository, "recent_event_counts", AsyncMock(return_value=[
        {"instance_name": "prod", "alert_key": "job_failed", "severity": "CRITICAL", "events": 2}]))


@pytest.mark.asyncio
async def test_checklist_summarizes_open_alerts_events_and_failing_checks(fleet):
    event = await digest.build_digest(NOW)
    assert (event.kind, event.new_severity) == ("digest", "CRITICAL") and event.dashboard_link.endswith("/alerts")
    lines = event.description.splitlines()
    assert lines[:2] == ["Daily DB checklist", "2 instance(s) checked; 1 with nothing open."]
    assert "  CRITICAL Disk Space — CRITICAL E:\\: 3 GB" in lines
    assert "  2 Job Failed event(s) in 24h (CRITICAL)" in lines
    assert "  1 check(s) could not run: Login Failed" in lines
    assert "gone" not in event.description  # deleted instances are left out


@pytest.mark.asyncio
async def test_sends_once_per_day_after_the_hour(fleet, monkeypatch):
    setting = {"enabled": True, "hour_utc": 7, "channel_ids": [1, 2], "last_sent_on": None}
    monkeypatch.setattr(alerts_repository, "get_digest_setting", AsyncMock(return_value=setting))
    claim = AsyncMock(return_value=True)
    monkeypatch.setattr(alerts_repository, "claim_digest", claim)
    enqueue = AsyncMock(return_value=2)
    monkeypatch.setattr(alerts_repository, "enqueue_digest", enqueue)
    assert not await digest.send_if_due(NOW.replace(hour=6))
    assert await digest.send_if_due(NOW)
    claim.assert_awaited_once_with(date(2026, 10, 5))
    assert enqueue.await_args.args[0] == [1, 2] and enqueue.await_args.args[2:] == ("Fleet", "daily_checklist")
    claim.return_value = False  # another worker already sent it
    assert not await digest.send_if_due(NOW)
    setting["last_sent_on"] = date(2026, 10, 5)
    assert not await digest.send_if_due(NOW)
