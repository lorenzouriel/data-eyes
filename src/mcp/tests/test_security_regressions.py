import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from data_eyes_mcp import config, repository_tools
from data_eyes_mcp.http_auth import BearerAuthMiddleware
from data_eyes_mcp.security import AuthorizationError, authorize_adhoc_sql
from data_eyes_mcp.tools import _creds_from_ctx


@pytest.mark.asyncio
async def test_http_requires_token_and_ignores_forged_identity(monkeypatch):
    token = "synthetic-random-token-for-unit-tests"
    monkeypatch.setattr(config.settings, "HTTP_TOKEN_HASHES", {"alice": hashlib.sha256(token.encode()).hexdigest()})
    async def app(scope, receive, send):
        if scope["path"] == "/health":
            return await JSONResponse({"ok": True})(scope, receive, send)
        ctx = SimpleNamespace(request_context=SimpleNamespace(request=Request(scope)))
        await JSONResponse(_creds_from_ctx(ctx))(scope, receive, send)
    transport = httpx.ASGITransport(app=BearerAuthMiddleware(app))
    forged = {"X-Data-Eyes-Principal": "admin", "X-Data-Eyes-Principal-B64": "YWRtaW4="}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/mcp", headers=forged)).status_code == 401
        assert (await client.get("/info")).status_code == 401
        assert (await client.get("/health")).status_code == 200
        response = await client.post("/mcp", headers={**forged, "Authorization": f"Bearer {token}"})
        assert response.json()["principal"] == "alice"
        assert (await client.post("/mcp", headers={"Authorization": "Bearer wrong"})).status_code == 401


def test_http_never_falls_back_to_stdio_principal(monkeypatch):
    monkeypatch.setattr(config.settings, "MCP_TRANSPORT", "http")
    monkeypatch.setattr(config.settings, "DEFAULT_PRINCIPAL", "admin")
    with pytest.raises(AuthorizationError):
        _creds_from_ctx(None)


@pytest.mark.asyncio
async def test_real_mcp_transport_preserves_verified_principal(monkeypatch):
    from data_eyes_mcp import tools, security
    token = "synthetic-transport-token"
    monkeypatch.setattr(config.settings, "HTTP_TOKEN_HASHES", {"alice": hashlib.sha256(token.encode()).hexdigest()})
    monkeypatch.setattr(config.settings, "MCP_TRANSPORT", "http")
    monkeypatch.setattr(config.settings, "DEFAULT_PRINCIPAL", "wrong-default")
    monkeypatch.setattr(tools, "load_instances", lambda: [SimpleNamespace(name="dev", label="visible-development", environment="development")])
    monkeypatch.setattr(security, "load_security_config", lambda: config.SecurityConfig(principals={
        "alice": config.PrincipalPolicy(tools=["list_configured_instances"], instances=["dev"])
    }))
    app = tools.mcp.streamable_http_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=BearerAuthMiddleware(app)), base_url="http://localhost:8080") as client:
            response = await client.post("/mcp", headers={
                "Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream",
                "X-Data-Eyes-Principal": "wrong-default", "X-Data-Eyes-Principal-B64": "d3JvbmctZGVmYXVsdA==",
            }, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "list_configured_instances", "arguments": {}
            }})
            assert response.status_code == 200
            assert "visible-development" in response.text


@pytest.mark.parametrize("sql", [
    "SELECT public FROM dbo.allowed UNION SELECT secret FROM dbo.allowed",
    "SELECT s.public FROM dbo.allowed a, dbo.secret s",
    "SELECT public FROM dbo.allowed WHERE secret=123",
    "SELECT public FROM dbo.allowed",
])
def test_adhoc_is_disabled_even_if_enforcement_is_misconfigured(sql, monkeypatch):
    monkeypatch.setattr(config.settings, "SECURITY_ENFORCEMENT", False)
    with pytest.raises(AuthorizationError, match="disabled"):
        authorize_adhoc_sql(sql, "Sales", "dev")


@pytest.mark.asyncio
async def test_repository_discovery_filters_principal_and_deployment(monkeypatch):
    monkeypatch.setattr(config.settings, "DEFAULT_PRINCIPAL", "alice")
    monkeypatch.setattr(repository_tools, "authorize", lambda **kwargs: None)
    monkeypatch.setattr(repository_tools, "enforce_rate_limit", lambda: None)
    monkeypatch.setattr(repository_tools, "is_authorized", lambda **kwargs: kwargs["instance"] != "other-dev")
    monkeypatch.setattr(repository_tools, "load_instances", lambda: [SimpleNamespace(name="dev"), SimpleNamespace(name="other-dev")])
    rows = [{"name": name, "label": name, "environment": "test"} for name in ("dev", "other-dev", "prod")]
    class Connection:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def fetch(self, sql):
            assert "mcp_instance_summary" in sql
            return rows
    monkeypatch.setattr(repository_tools, "_get_pool", AsyncMock(return_value=SimpleNamespace(acquire=lambda: Connection())))
    result = json.loads(await repository_tools.list_tracked_instances())
    assert [row["name"] for row in result["rows"]] == ["dev"]
