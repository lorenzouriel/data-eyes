from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.notifications import dispatcher
from app.notifications.models import DeliveryResult, RuleInput

NOW = datetime(2026, 10, 2, 23, 0, tzinfo=timezone.utc)


def snapshot(severity="CRITICAL", category="backup"):
    return {"instance_name": "prod one", "category": category, "severity": severity,
            "metric_value": 3, "captured_at": NOW}


def state(severity="OK", category="backup"):
    return {**snapshot(severity, category), "captured_at": NOW - timedelta(minutes=1)}


def rule(**kwargs):
    return {"id": 1, **RuleInput(name="alerts", channel_id=1, **kwargs).model_dump()}


def test_only_transitions_and_no_initial_alert():
    assert dispatcher.plan([snapshot()], [], [rule()], [], NOW) == []
    assert dispatcher.plan([snapshot()], [state("CRITICAL")], [rule()], [], NOW) == []
    planned = dispatcher.plan([snapshot()], [state()], [rule()], [], NOW)
    assert len(planned) == 1
    _, event, reason = planned[0]
    assert event.old_severity == "OK" and event.new_severity == "CRITICAL"
    assert event.metric_value == 3 and event.dashboard_link.endswith("/prod%20one")
    assert not reason


def test_cooldown_and_expiry_are_per_rule_instance_category():
    previous = [{"rule_id": 1, "instance_name": "prod one", "category": "backup", "last_sent": NOW - timedelta(seconds=30)}]
    assert dispatcher.plan([snapshot()], [state()], [rule(cooldown_seconds=60)], previous, NOW)[0][2] == "Cooldown"
    assert dispatcher.plan([snapshot()], [state()], [rule(cooldown_seconds=20)], previous, NOW)[0][2] == ""
    assert dispatcher.plan([snapshot()], [state()], [rule(cooldown_seconds=0)], previous, NOW)[0][2] == ""


@pytest.mark.parametrize("before", ["WARNING", "CRITICAL"])
def test_recovery_is_opt_in(before):
    assert dispatcher.plan([snapshot("OK")], [state(before)], [rule()], [], NOW) == []
    result = dispatcher.plan([snapshot("OK")], [state(before)], [rule(recovery=True)], [], NOW)
    assert result[0][1].new_severity == "OK"
    assert dispatcher.plan([snapshot("OK")], [state("UNKNOWN")], [rule(recovery=True)], [], NOW) == []


@pytest.mark.parametrize("hour,quiet", [(21, False), (22, True), (23, True), (0, True), (6, False)])
def test_overnight_quiet_hours(hour, quiet):
    r = rule(quiet_start=22, quiet_end=6)
    assert dispatcher.in_quiet_hours(r, NOW.replace(hour=hour)) == quiet
    assert bool(dispatcher.plan([snapshot()], [state()], [r], [], NOW.replace(hour=hour))[0][2]) == quiet


def test_daytime_quiet_hours_and_filters():
    assert dispatcher.in_quiet_hours(rule(quiet_start=9, quiet_end=17), NOW.replace(hour=10))
    assert not dispatcher.in_quiet_hours(rule(quiet_start=9, quiet_end=17), NOW.replace(hour=17))
    for r in [rule(instance="other"), rule(category="errors"), rule(enabled=False), rule(severities=["WARNING"])]:
        assert dispatcher.plan([snapshot()], [state()], [r], [], NOW) == []


def test_grouping_retains_all_events_and_uses_instance_cooldown():
    snapshots = [snapshot(), snapshot("WARNING", "errors")]
    states = [state(), state(category="errors")]
    r = rule(group_by_instance=True, severities=["WARNING", "CRITICAL"])
    result = dispatcher.plan(snapshots, states, [r], [], NOW)
    assert len(result) == 1 and len(result[0][1].grouped) == 2
    assert result[0][1].category == "*" and result[0][1].new_severity == "CRITICAL"
    assert "errors" in result[0][1].description and "value: 3" in result[0][1].description


def test_stale_snapshot_does_not_revert_state():
    assert dispatcher.plan([snapshot()], [{**state(), "captured_at": NOW}], [rule()], [], NOW) == []


@pytest.mark.asyncio
async def test_failing_channel_does_not_block_other_deliveries(monkeypatch):
    event = dispatcher.plan([snapshot()], [state()], [rule()], [], NOW)[0][1]
    rows = [{"id": i, "channel_id": i, "attempts": 1, "event": event.model_dump_json()} for i in (1, 2)]
    monkeypatch.setattr(dispatcher.repository, "enqueue_notifications", AsyncMock())
    monkeypatch.setattr(dispatcher.repository, "claim_notification", AsyncMock(side_effect=[*rows, None, None]))
    monkeypatch.setattr(dispatcher.repository, "get_notification_channel", AsyncMock(side_effect=[
        {"enabled": True, "type": "bad", "config": {}}, {"enabled": True, "type": "good", "config": {}}]))
    finish = AsyncMock()
    monkeypatch.setattr(dispatcher.repository, "finish_notification", finish)
    bad = AsyncMock(side_effect=RuntimeError("secret-webhook-url"))
    good = AsyncMock(return_value=DeliveryResult(ok=True))
    monkeypatch.setitem(dispatcher.REGISTRY, "bad", lambda: type("Bad", (), {"send": bad})())
    monkeypatch.setitem(dispatcher.REGISTRY, "good", lambda: type("Good", (), {"send": good})())
    await dispatcher.evaluate()
    assert finish.await_count == 2
    results = [call.args[1] for call in finish.await_args_list]
    assert {r.ok for r in results} == {True, False}
    assert "secret" not in str(results)


@pytest.mark.asyncio
async def test_collector_evaluates_after_all_snapshot_jobs(monkeypatch):
    from app import collector
    monkeypatch.setattr(collector.repository, "list_instances", AsyncMock(return_value=[object()]))
    jobs = []
    for name in ("_collect_instance", "_collect_wait_categories", "_collect_blocking_event", "_collect_resource_rates",
                 "_collect_file_io", "_collect_deadlocks", "_collect_error_rate"):
        mock = AsyncMock()
        jobs.append(mock)
        monkeypatch.setattr(collector, name, mock)
    async def evaluated(since):
        assert since.tzinfo is timezone.utc
        assert all(job.await_count == 1 for job in jobs)
    evaluate = AsyncMock(side_effect=evaluated)
    monkeypatch.setattr(dispatcher, "evaluate", evaluate)
    await collector._collect_once()
    evaluate.assert_awaited_once()
    evaluate.side_effect = RuntimeError("notification failure")
    await collector._collect_once()  # Delivery failures never kill collection.
    monkeypatch.setattr(collector.repository, "list_instances", AsyncMock(return_value=[]))
    evaluate.side_effect = None
    await collector._collect_once()  # Drain outstanding retries even with no instances.
    assert evaluate.await_count == 3
