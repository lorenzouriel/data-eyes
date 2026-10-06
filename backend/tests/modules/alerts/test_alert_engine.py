from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pyodbc
import pytest

from app.infrastructure.sqlserver.client import MSSQLError
from app.modules.alerts import engine
from app.modules.alerts.catalog import CATALOG
from app.modules.alerts.models import Finding
from app.modules.alerts.models import Occurrence

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
PROD = SimpleNamespace(name="prod", mssql_connection_string="Driver=x;Server=prod")


def failure(message, cause=None):
    error = MSSQLError(message)
    error.__cause__ = cause
    return error


@pytest.fixture
def repo(monkeypatch):
    """In-memory alert repository; only two alerts enabled so tests stay focused."""
    store = SimpleNamespace(states={}, events=[], memory={}, snapshots=[])
    enabled = {"sql_server_connection", "disk_space", "job_failed"}
    settings_rows = [{"alert_key": d.key, "instance_name": "", "enabled": d.key in enabled, "warning_threshold": None,
                      "critical_threshold": None, "tier": None, "confirm_samples": 1, "excluded_databases": None} for d in CATALOG]
    from app.modules.alerts import repository
    from app.modules.monitoring import repository as monitoring_repository
    monkeypatch.setattr(repository, "list_settings", AsyncMock(return_value=settings_rows))
    monkeypatch.setattr(repository, "list_states", AsyncMock(side_effect=lambda: [
        {"instance_name": i, "alert_key": k, **v} for (i, k), v in store.states.items()]))

    async def save_state(instance, key, state):
        store.states[(instance, key)] = state

    async def insert_events(instance, key, rows):
        new = [r for r in rows if r["dedup_key"] not in {e["dedup_key"] for e in store.events}]
        store.events += new
        return new

    async def save_memory(instance, key, memory):
        store.memory[(instance, key)] = memory

    async def snapshot(instance, category, severity, metric):
        store.snapshots.append((instance, category, severity, metric))

    monkeypatch.setattr(repository, "save_state", save_state)
    monkeypatch.setattr(repository, "insert_events", insert_events)
    monkeypatch.setattr(repository, "save_memory", save_memory)
    monkeypatch.setattr(repository, "load_memory", AsyncMock(side_effect=lambda instance: {
        k: v for (i, k), v in store.memory.items() if i == instance}))
    monkeypatch.setattr(monitoring_repository, "insert_category_snapshot", snapshot)
    monkeypatch.setattr(engine, "_last_run", {})
    return store


@pytest.fixture
def checks(monkeypatch):
    disk = AsyncMock(return_value=[Finding("E:\\", 3.0)])
    jobs = AsyncMock(return_value=[Occurrence("42", NOW, "Nightly backup", floor="CRITICAL")])
    monkeypatch.setitem(engine.CHECKS, "disk_space", disk)
    monkeypatch.setitem(engine.CHECKS, "job_failed", jobs)
    return SimpleNamespace(disk=disk, jobs=jobs)


@pytest.mark.asyncio
async def test_records_state_snapshot_and_events(monkeypatch, repo, checks):
    monkeypatch.setattr(engine, "_query", AsyncMock(return_value=[{"Reachable": 1}]))
    await engine.run_cycle([PROD], NOW)
    assert repo.states[("prod", "disk_space")]["severity"] == "CRITICAL"
    assert "E:\\: 3 GB" in repo.states[("prod", "disk_space")]["detail"]
    assert ("prod", "alert.disk_space", "CRITICAL", 3.0) in repo.snapshots
    assert ("prod", "alert.sql_server_connection", "OK", None) in repo.snapshots
    assert [e["dedup_key"] for e in repo.events] == ["42"]
    # Event alerts are delivered through alert_event, never as snapshot transitions.
    assert not any(category == "alert.job_failed" for _, category, _, _ in repo.snapshots)


@pytest.mark.asyncio
async def test_unreachable_instance_raises_only_connection_alert(monkeypatch, repo, checks):
    monkeypatch.setattr(engine, "_query", AsyncMock(side_effect=failure("SQL Server connection failed; check server")))
    await engine.run_cycle([PROD], NOW)
    state = repo.states[("prod", "sql_server_connection")]
    assert state["severity"] == "CRITICAL" and "Connection failed" in state["detail"]
    checks.disk.assert_not_awaited()
    assert ("prod", "disk_space") not in engine._last_run  # runs as soon as the instance is back


@pytest.mark.asyncio
async def test_busy_lane_skips_without_false_outage(monkeypatch, repo, checks):
    monkeypatch.setattr(engine, "_query", AsyncMock(side_effect=failure("SQL query capacity exhausted; retry shortly")))
    await engine.run_cycle([PROD], NOW)
    assert repo.states == {} and repo.snapshots == []


@pytest.mark.asyncio
async def test_missing_permission_is_unknown_with_safe_message(monkeypatch, repo, checks):
    monkeypatch.setattr(engine, "_query", AsyncMock(return_value=[{"Reachable": 1}]))
    secret = pyodbc.Error("42000", "[Microsoft] The SELECT permission was denied on object 'backupset' Pwd=hunter2")
    checks.disk.side_effect = failure("SQL diagnostic query failed", secret)
    await engine.run_cycle([PROD], NOW)
    state = repo.states[("prod", "disk_space")]
    assert (state["severity"], state["status"], state["status_message"]) == ("UNKNOWN", "error", "Missing permission")
    assert "hunter2" not in str(repo.states)


@pytest.mark.asyncio
async def test_watermarks_persist_only_after_success(monkeypatch, repo, checks):
    monkeypatch.setattr(engine, "_query", AsyncMock(return_value=[{"Reachable": 1}]))

    async def advancing(ctx):
        ctx.memory["last_instance_id"] = 42
        return []

    async def failing(ctx):
        ctx.memory["last_instance_id"] = 99
        raise failure("SQL diagnostic query failed")

    checks.jobs.side_effect = advancing
    await engine.run_cycle([PROD], NOW)
    assert repo.memory[("prod", "job_failed")] == {"last_instance_id": 42}
    checks.jobs.side_effect = failing
    await engine.run_cycle([PROD], NOW + timedelta(minutes=10))
    assert repo.memory[("prod", "job_failed")] == {"last_instance_id": 42}
    assert repo.states[("prod", "job_failed")]["status"] == "error"


@pytest.mark.asyncio
async def test_tiers_and_disabled_alerts(monkeypatch, repo, checks):
    monkeypatch.setattr(engine, "_query", AsyncMock(return_value=[{"Reachable": 1}]))
    await engine.run_cycle([PROD], NOW)
    await engine.run_cycle([PROD], NOW + timedelta(minutes=1))  # disk_space is a 5-minute "standard" check
    assert checks.disk.await_count == 1
    await engine.run_cycle([PROD], NOW + timedelta(minutes=5))
    assert checks.disk.await_count == 2
    assert ("prod", "cpu_utilization") not in repo.states  # disabled in this fixture
    engine.forget("disk_space")
    await engine.run_cycle([PROD], NOW + timedelta(minutes=6))
    assert checks.disk.await_count == 3


@pytest.mark.asyncio
async def test_double_check_holds_snapshot_until_confirmed(monkeypatch, repo, checks):
    monkeypatch.setattr(engine, "_query", AsyncMock(return_value=[{"Reachable": 1}]))
    repo.states[("prod", "disk_space")] = {"severity": "OK", "observed_severity": "OK", "streak": 3, "changed_at": NOW}
    from app.modules.alerts import repository
    rows = await repository.list_settings()
    next(r for r in rows if r["alert_key"] == "disk_space")["confirm_samples"] = 2
    await engine.run_cycle([PROD], NOW)
    assert repo.states[("prod", "disk_space")]["severity"] == "OK"
    engine.forget("disk_space")
    await engine.run_cycle([PROD], NOW + timedelta(minutes=1))
    assert repo.states[("prod", "disk_space")]["severity"] == "CRITICAL"
    assert repo.states[("prod", "disk_space")]["changed_at"] == NOW + timedelta(minutes=1)


@pytest.mark.parametrize("message,cause,expected", [
    ("SQL query capacity exhausted; retry shortly", None, engine.BUSY),
    ("Query exceeded 30s timeout", None, "Timed out"),
    ("SQL diagnostic query failed", "Invalid object name 'sys.dm_db_log_stats'", "Not supported on this server"),
    ("SQL diagnostic query failed", "EXECUTE permission was denied on xp_readerrorlog", "Missing permission"),
    ("SQL diagnostic query failed", "Arithmetic overflow", "Query failed"),
])
def test_classify(message, cause, expected):
    assert engine.classify(failure(message, Exception(cause) if cause else None)) == expected
