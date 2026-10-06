from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request

import app.modules.alerts.repository as alerts_repository
import app.modules.instances.repository as instances_repository
from app.modules.alerts import engine
from app.modules.alerts.router import router
from app.modules.auth import router as auth


def client_for(role, routes=router):
    app = FastAPI()
    app.include_router(routes)

    async def user(request: Request):
        request.state.user = {"role": role}
        return role
    app.dependency_overrides[auth.require_auth] = user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


def stored(**values):
    return {"alert_key": "disk_space", "instance_name": "", "enabled": None, "warning_threshold": None,
            "critical_threshold": None, "tier": None, "confirm_samples": None, "excluded_databases": None, **values}


@pytest.fixture
def repo(monkeypatch):
    calls = SimpleNamespace(settings=[], reset=AsyncMock())
    monkeypatch.setattr(alerts_repository, "list_settings", AsyncMock(side_effect=lambda: list(calls.settings)))
    monkeypatch.setattr(alerts_repository, "upsert_setting", AsyncMock(side_effect=lambda data: stored(**data)))
    monkeypatch.setattr(alerts_repository, "reset_alert", calls.reset)
    monkeypatch.setattr(instances_repository, "get_instance", AsyncMock(side_effect=lambda name: name == "prod" or None))
    monkeypatch.setattr(engine, "_last_run", {("prod", "disk_space"): object()})
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", [
    ("PUT", "/api/alerts/settings", {"alert_key": "disk_space", "enabled": False}),
    ("DELETE", "/api/alerts/settings?alert_key=disk_space", None),
    ("GET", "/api/alerts/digest", None), ("PUT", "/api/alerts/digest", {"enabled": True}),
])
async def test_changes_require_admin(method, path, payload):
    async with client_for("member") as client:
        response = await client.request(method, path, json=payload)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_members_can_read_catalog(repo):
    async with client_for("member") as client:
        response = await client.get("/api/alerts/catalog")
    assert response.status_code == 200
    alerts = {a["key"]: a for a in response.json()["alerts"]}
    assert alerts["disk_space"]["direction"] == "below" and alerts["disk_space"]["has_thresholds"]
    assert alerts["index_fragmentation"]["default_enabled"] is False


@pytest.mark.asyncio
async def test_disabling_resets_state_so_reenabling_starts_a_baseline(repo):
    async with client_for("admin") as client:
        response = await client.put("/api/alerts/settings", json={"alert_key": "disk_space", "instance_name": "prod", "enabled": False})
    assert response.status_code == 200
    repo.reset.assert_awaited_once_with("disk_space", "prod")
    assert engine._last_run == {}
    repo.reset.reset_mock()
    async with client_for("admin") as client:
        await client.put("/api/alerts/settings", json={"alert_key": "disk_space", "warning_threshold": 40, "critical_threshold": 10})
    repo.reset.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,status", [
    ({"alert_key": "nope"}, 404),
    ({"alert_key": "disk_space", "warning_threshold": 5, "critical_threshold": 20}, 422),  # "below": warning must be higher
    ({"alert_key": "transaction_log_health", "warning_threshold": 95, "critical_threshold": 90}, 422),
    ({"alert_key": "sa_enabled", "warning_threshold": 1}, 422),  # fixed-severity alert
    ({"alert_key": "disk_space", "excluded_databases": ["Dev"]}, 422),  # drive-level, not per database
    ({"alert_key": "notification_delivery_failing", "instance_name": "prod"}, 422),
    ({"alert_key": "disk_space", "instance_name": "missing"}, 404),
    ({"alert_key": "disk_space", "confirm_samples": 11}, 422),
    ({"alert_key": "disk_space", "warning_threshold": "NaN"}, 422),
])
async def test_setting_validation(repo, payload, status):
    async with client_for("admin") as client:
        response = await client.put("/api/alerts/settings", json=payload)
    assert response.status_code == status


@pytest.mark.asyncio
async def test_excluded_databases_are_trimmed_and_deduplicated(repo):
    async with client_for("admin") as client:
        response = await client.put("/api/alerts/settings", json={"alert_key": "full_backup_age", "excluded_databases": [" Dev ", "Dev", ""]})
    assert response.json()["excluded_databases"] == ["Dev"]


@pytest.mark.asyncio
async def test_digest_rejects_unknown_channels(monkeypatch):
    monkeypatch.setattr(alerts_repository, "channel_ids", AsyncMock(return_value=[1]))
    save = AsyncMock(return_value={"enabled": True, "hour_utc": 6, "channel_ids": [1], "last_sent_on": None})
    monkeypatch.setattr(alerts_repository, "save_digest_setting", save)
    async with client_for("admin") as client:
        assert (await client.put("/api/alerts/digest", json={"enabled": True, "channel_ids": [2]})).status_code == 422
        assert (await client.put("/api/alerts/digest", json={"enabled": True, "hour_utc": 6, "channel_ids": [1, 1]})).status_code == 200
    save.assert_awaited_once_with(True, 6, [1])


@pytest.mark.asyncio
async def test_rules_only_accept_catalog_categories(monkeypatch):
    import app.modules.notifications.repository as notifications_repository
    from app.modules.notifications.router import router as notifications_router
    monkeypatch.setattr(notifications_repository, "get_notification_channel", AsyncMock(return_value={"type": "slack"}))
    monkeypatch.setattr(notifications_repository, "save_notification_rule", AsyncMock(return_value={"id": 1}))
    async with client_for("admin", notifications_router) as client:
        rejected = await client.post("/api/notifications/rules", json={"name": "x", "channel_id": 1, "category": "backup_health"})
        accepted = await client.post("/api/notifications/rules", json={"name": "x", "channel_id": 1, "category": "full_backup_age",
                                                                         "renotify_seconds": 3600})
    assert rejected.status_code == 422 and accepted.status_code == 201
