import asyncio
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Depends, FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app import auth, passwords, repository, mssql_client
from app.config import settings
from app.connection_policy import parse_connection_string, validate_connection_string
from app.insights_agent import _compact_context
from app.routers import users, instances, insights
from app.ai_provider import AIProviderError, LimitedProvider


@pytest.fixture
def session_app(monkeypatch):
    users_db = {"alice": {"username": "alice", "role": "admin", "password_hash": passwords.hash_password("original-password")}}
    sessions = {}

    async def lookup(name):
        return users_db.get(name)

    async def create(token, username, expected, lifetime):
        if users_db[username]["password_hash"] != expected:
            return False
        sessions[token] = username
        return True

    async def validate(token):
        return users_db.get(sessions.get(token))

    async def revoke(token):
        sessions.pop(token, None)

    async def change(username, password_hash, expected):
        if users_db[username]["password_hash"] != expected:
            return False
        users_db[username]["password_hash"] = password_hash
        for token in list(sessions):
            if sessions[token] == username:
                sessions.pop(token)
        return True

    monkeypatch.setattr(repository, "get_user_by_username", lookup)
    monkeypatch.setattr(repository, "create_session", create)
    monkeypatch.setattr(repository, "get_session_user", validate)
    monkeypatch.setattr(repository, "revoke_session", revoke)
    monkeypatch.setattr(repository, "update_user_password", change)
    monkeypatch.setattr(repository, "consume_quota", AsyncMock(return_value=True))
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET_KEY, https_only=True, same_site="strict")
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(instances.router)

    @app.get("/admin")
    async def admin(username=Depends(auth.require_admin)):
        return {"username": username}

    return app, users_db, sessions


async def sign_in(client):
    response = await client.post("/api/auth/login", json={"username": "alice", "password": "original-password"})
    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()
    assert "httponly" in response.headers["set-cookie"].lower()
    return client.cookies.get("session")


@pytest.mark.asyncio
async def test_revocation_and_current_role(session_app):
    app, users_db, _ = session_app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        stolen = await sign_in(client)
        users_db["alice"]["role"] = "member"
        assert (await client.get("/admin")).status_code == 403
        assert (await client.post("/api/instances/test-connection", json={})).status_code == 403
        users_db.pop("alice")
        assert (await client.get("/api/auth/me", headers={"cookie": f"session={stolen}"})).status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_replayed_cookie(session_app):
    app, _, _ = session_app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        stolen = await sign_in(client)
        assert (await client.post("/api/auth/logout")).status_code == 200
        assert (await client.get("/api/auth/me", headers={"cookie": f"session={stolen}"})).status_code == 401


@pytest.mark.asyncio
async def test_password_requires_reauthentication_and_revokes_all_sessions(session_app):
    app, _, sessions = session_app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        stolen = await sign_in(client)
        response = await client.post("/api/users/me/password", json={"password": "replacement-password", "current_password": "wrong"})
        assert response.status_code == 403
        assert sessions
        response = await client.post("/api/users/me/password", json={"password": "replacement-password", "current_password": "original-password"})
        assert response.status_code == 200
        assert not sessions
        assert (await client.get("/api/auth/me", headers={"cookie": f"session={stolen}"})).status_code == 401


@pytest.mark.asyncio
async def test_login_throttles_before_password_work(session_app, monkeypatch):
    app, _, _ = session_app
    monkeypatch.setattr(repository, "consume_quota", AsyncMock(return_value=False))
    work = AsyncMock()
    monkeypatch.setattr(auth, "password_work", work)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        response = await client.post("/api/auth/login", json={"username": "alice", "password": "guess"})
    assert response.status_code == 429
    work.assert_not_called()


def test_odbc_policy_blocks_unapproved_destinations_and_options(monkeypatch):
    monkeypatch.setattr(settings, "SQL_ALLOWED_SERVERS", ["sql.internal,1433"])
    safe = "Driver={ODBC Driver 18 for SQL Server};Server=sql.internal,1433;UID=monitor;PWD={p;ass}}word};Encrypt=yes;TrustServerCertificate=no"
    assert validate_connection_string(safe) == safe
    assert parse_connection_string(safe)["pwd"] == "p;ass}word"
    assert parse_connection_string(mssql_client._apply_database(safe, "other;catalog"))["database"] == "other;catalog"
    for bad in [safe.replace("sql.internal", "attacker.test"), safe + ";Server=other", safe + ";TraceFile=/tmp/trace", safe.replace("Certificate=no", "Certificate=yes")]:
        with pytest.raises(ValueError):
            validate_connection_string(bad)


def test_ai_context_removes_sql_literals_and_free_text():
    output = _compact_context({"blocking": [{"severity": "CRITICAL", "BlockedQueryText": "SELECT 'secret-token'", "HostName": "private-host", "duration": 42}], "top_query_plan": {"literal": "secret-token"}})
    assert "secret-token" not in output and "private-host" not in output
    assert "42" in output and "CRITICAL" in output


def test_chat_history_limits():
    with pytest.raises(ValueError):
        insights.AskRequest(messages=[{"role": "user", "content": "a" * 4001}])
    with pytest.raises(ValueError):
        insights.AskRequest(messages=[{"role": "user", "content": "a" * 4000}] * 4)


@pytest.mark.asyncio
async def test_timeout_cancels_and_keeps_capacity_until_worker_exits(monkeypatch):
    entered, cancelled, finish = threading.Event(), threading.Event(), threading.Event()
    class Cursor:
        description = None
        def execute(self, sql):
            entered.set()
            finish.wait(5)
        def cancel(self):
            cancelled.set()
        def close(self):
            pass
    connection = SimpleNamespace(cursor=lambda: Cursor(), timeout=0)
    @contextmanager
    def connect(*args, **kwargs):
        yield connection
    monkeypatch.setattr(mssql_client, "_get_connection", connect)
    monkeypatch.setattr(mssql_client, "_query_slots", {"interactive": asyncio.Semaphore(1)})
    task = asyncio.create_task(mssql_client.execute_query("synthetic", "SELECT 1"))
    try:
        await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await asyncio.to_thread(cancelled.wait, 1)
        assert mssql_client._query_slots["interactive"].locked()
        assert connection.timeout == 30
    finally:
        finish.set()
        for _ in range(100):
            if not mssql_client._query_slots["interactive"].locked():
                break
            await asyncio.sleep(0.01)
    assert not mssql_client._query_slots["interactive"].locked()


@pytest.mark.asyncio
async def test_ai_quota_blocks_provider(monkeypatch):
    from app import security_limits
    from fastapi import HTTPException
    monkeypatch.setattr(security_limits, "quota", AsyncMock(side_effect=HTTPException(429)))
    provider = SimpleNamespace(status=SimpleNamespace(), complete_text=AsyncMock())
    limited = LimitedProvider(provider)
    with pytest.raises(AIProviderError, match="limit"):
        await limited.complete_text(system="", messages=[], tier="routine", max_tokens=1)
    provider.complete_text.assert_not_called()
