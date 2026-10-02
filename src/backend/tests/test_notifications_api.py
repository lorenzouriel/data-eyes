from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request

from app import auth, crypto, repository
from app.notifications.models import MASK
from app.routers.notifications import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    async def admin(request: Request):
        request.state.user = {"role": "admin"}
        return "admin"
    app.dependency_overrides[auth.require_auth] = admin
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", [
    ("GET", "/channels", None), ("POST", "/channels", {"name": "test", "type": "slack", "config": {}}),
    ("PUT", "/channels/1", {"name": "test", "type": "slack", "config": {}}),
    ("DELETE", "/channels/1", None), ("POST", "/channels/1/test", None),
    ("GET", "/rules", None), ("POST", "/rules", {"name": "test", "channel_id": 1}),
    ("PUT", "/rules/1", {"name": "test", "channel_id": 1}), ("DELETE", "/rules/1", None),
    ("GET", "/logs", None), ("DELETE", "/logs/1", None),
])
async def test_all_endpoints_require_admin(app, method, path, payload):
    async def member(request: Request):
        request.state.user = {"role": "member"}
        return "member"
    app.dependency_overrides[auth.require_auth] = member
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        response = await client.request(method, "/api/notifications" + path, json=payload)
    assert response.status_code == 403


@pytest.fixture
def db(monkeypatch):
    conn = AsyncMock()
    @asynccontextmanager
    async def acquire():
        yield conn
    monkeypatch.setattr(repository, "notification_connection", acquire)
    return conn


@pytest.mark.asyncio
async def test_create_encrypts_at_rest_and_masks_response(app, db):
    secret = "https://hooks.example/never-return-this-secret"
    async def inserted(query, name, kind, enabled, encrypted):
        assert isinstance(encrypted, bytes)
        assert secret.encode() not in encrypted
        assert secret in crypto.decrypt(encrypted)
        return {"id": 1, "name": name, "type": kind, "enabled": enabled, "config": encrypted}
    db.fetchrow.side_effect = inserted
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        response = await client.post("/api/notifications/channels", json={"name": "Slack", "type": "slack", "config": {"webhook_url": secret}})
    assert response.status_code == 201 and secret not in response.text
    assert response.json()["config"]["webhook_url"] == MASK


@pytest.mark.asyncio
async def test_list_masks_all_credentials(app, db):
    import json
    secrets = {key: f"secret-{key}" for key in ["webhook_url", "username", "password", "account_sid", "auth_token"]}
    db.fetch.return_value = [{"id": 1, "name": "test", "type": "email", "enabled": True, "config": crypto.encrypt(json.dumps(secrets))}]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get("/api/notifications/channels")
    assert response.status_code == 200
    assert all(value not in response.text for value in secrets.values())
    assert set(response.json()[0]["config"].values()) == {MASK}


@pytest.mark.asyncio
async def test_update_preserves_masked_secret(app, monkeypatch):
    secret = "https://hooks.example/keep-secret"
    monkeypatch.setattr(repository, "get_notification_channel", AsyncMock(return_value={"type": "slack", "config": {"webhook_url": secret}}))
    save = AsyncMock(return_value={"id": 1, "config": {"webhook_url": MASK}})
    monkeypatch.setattr(repository, "save_notification_channel", save)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        response = await client.put("/api/notifications/channels/1", json={"name": "new", "type": "slack", "config": {"webhook_url": MASK}})
    assert response.status_code == 200 and secret not in response.text
    assert save.call_args.args[0]["config"]["webhook_url"] == secret


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"name": "test", "type": "invalid-secret", "config": {"password": "never-echo"}},
    {"name": "test", "type": "slack", "config": {"webhook_url": "never-echo"}},
    {"name": "test", "type": "slack", "config": "never-echo"},
])
async def test_validation_errors_never_echo_secrets(app, payload):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        response = await client.post("/api/notifications/channels", json=payload)
    assert response.status_code == 422 and "never-echo" not in response.text and "invalid-secret" not in response.text


@pytest.mark.asyncio
async def test_test_endpoint_sanitizes_exception_and_logs_failure(app, monkeypatch):
    from app.routers import notifications
    monkeypatch.setattr(repository, "get_notification_channel", AsyncMock(return_value={"type": "slack", "config": {}}))
    log = AsyncMock()
    monkeypatch.setattr(repository, "log_notification_test", log)
    notifier = type("Failing", (), {"test": AsyncMock(side_effect=RuntimeError("never-echo"))})
    monkeypatch.setitem(notifications.REGISTRY, "slack", notifier)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        response = await client.post("/api/notifications/channels/1/test")
    assert response.status_code == 200 and not response.json()["ok"] and "never-echo" not in response.text
    assert not log.call_args.args[2].ok


@pytest.mark.asyncio
async def test_rules_default_to_critical_only(app, monkeypatch):
    monkeypatch.setattr(repository, "get_notification_channel", AsyncMock(return_value={"type": "sms"}))
    save = AsyncMock(return_value={"id": 1})
    monkeypatch.setattr(repository, "save_notification_rule", save)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        response = await client.post("/api/notifications/rules", json={"name": "SMS", "channel_id": 1})
    assert response.status_code == 201
    assert save.call_args.args[0]["severities"] == ["CRITICAL"] and not save.call_args.args[0]["recovery"]
