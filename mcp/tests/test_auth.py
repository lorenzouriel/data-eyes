import hashlib
from types import SimpleNamespace

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from data_eyes_mcp import auth, config
from data_eyes_mcp.auth import AuthorizationError, BearerAuthMiddleware, authorize, principal_of

TOKEN = "synthetic-random-token-for-unit-tests"


@pytest.fixture
def tokens(monkeypatch):
    monkeypatch.setattr(config.settings, "HTTP_TOKEN_HASHES", {"alice": hashlib.sha256(TOKEN.encode()).hexdigest()})


async def test_http_requires_a_token_and_ignores_identity_headers(tokens):
    async def app(scope, receive, send):
        ctx = SimpleNamespace(request_context=SimpleNamespace(request=Request(scope)))
        await JSONResponse({"principal": principal_of(ctx)})(scope, receive, send)

    forged = {"X-Data-Eyes-Principal": "admin"}
    transport = httpx.ASGITransport(app=BearerAuthMiddleware(app))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/mcp", headers=forged)).status_code == 401
        assert (await client.get("/ready")).status_code == 401
        assert (await client.post("/mcp", headers={"Authorization": "Bearer wrong"})).status_code == 401
        response = await client.post("/mcp", headers={**forged, "Authorization": f"Bearer {TOKEN}"})
        assert response.json() == {"principal": "alice"}


async def test_websocket_scopes_are_not_waved_through(tokens):
    sent = []

    async def app(scope, receive, send):
        raise AssertionError("unauthenticated websocket reached the app")

    async def send(message):
        sent.append(message)

    await BearerAuthMiddleware(app)({"type": "websocket", "path": "/mcp", "headers": []}, None, send)
    assert sent[0]["status"] == 401


def test_http_never_falls_back_to_the_stdio_principal(fleet, monkeypatch):
    monkeypatch.setattr(auth, "http_mode", True)
    with pytest.raises(AuthorizationError):
        principal_of(None)


def test_grants_are_default_deny(fleet):
    authorize("alice", "sample_table", "dev")
    authorize("bob", "list_tables", "dev")
    for principal, tool, instance in [("bob", "sample_table", "dev"), ("bob", "list_tables", "beta"),
                                      ("alice", "list_tables", "prod"), ("nobody", "list_tables", "dev")]:
        with pytest.raises(AuthorizationError):
            authorize(principal, tool, instance)


def test_rate_limit_is_per_principal(fleet, monkeypatch):
    monkeypatch.setattr(config.settings, "RATE_LIMIT_PER_MINUTE", 2)
    authorize("alice", "list_tables", "dev")
    authorize("alice", "list_tables", "dev")
    authorize("bob", "list_tables", "dev")
    with pytest.raises(AuthorizationError, match="Rate limit"):
        authorize("alice", "list_tables", "dev")


async def test_real_mcp_transport_uses_the_verified_principal(fleet, tokens, monkeypatch):
    from data_eyes_mcp.tools import mcp

    monkeypatch.setattr(auth, "http_mode", True)
    app = mcp.streamable_http_app()
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json, text/event-stream",
               "X-Data-Eyes-Principal": "bob"}
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=BearerAuthMiddleware(app))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8080") as client:
            listed = await client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            called = await client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "list_configured_instances", "arguments": {}}})
    assert '"execute_sql"' not in listed.text and '"ctx"' not in listed.text
    assert '"sample_table"' in listed.text and '"instance"' in listed.text
    assert "Beta" in called.text  # alice's grant, not bob's
