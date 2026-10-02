from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from app.notifications import REGISTRY, base
from app.notifications.models import NotificationEvent, validate_config
from app.notifications.notifiers import email


@pytest.fixture
def event():
    return NotificationEvent(instance="prod1", category="Backup health", old_severity="OK", new_severity="CRITICAL",
                             metric_value=3, dashboard_link="https://eyes.example/instances/prod1", timestamp=datetime.now(timezone.utc))


@pytest.fixture
def requests(monkeypatch):
    seen = []
    real_client = httpx.AsyncClient
    def handle(request):
        seen.append(request)
        return httpx.Response(200)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["slack", "teams"])
async def test_webhook_payloads(kind, event, requests):
    import json
    result = await REGISTRY[kind]().send(event, {"webhook_url": "https://hooks.example/secret", "mention": "<@U123>"})
    assert result.ok
    body = json.loads(requests[0].content)
    if kind == "slack":
        assert body["attachments"][0]["color"] == "#dc2626"
        blocks = body["attachments"][0]["blocks"]
        assert blocks[-1]["elements"][0]["url"] == event.dashboard_link
        assert "value: 3" in blocks[1]["text"]["text"]
    else:
        assert body["type"] == "message"
        assert body["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
        card = body["attachments"][0]["content"]
        assert card["type"] == "AdaptiveCard" and card["actions"][0]["url"] == event.dashboard_link


@pytest.mark.asyncio
async def test_smtp_multipart_and_tls(event, monkeypatch):
    send = AsyncMock(return_value=({}, "accepted"))
    monkeypatch.setattr(email.aiosmtplib, "send", send)
    config = {"smtp_host": "smtp.example", "port": 587, "use_tls": True, "from_addr": "eyes@example.com", "to_addrs": ["ops@example.com"]}
    assert (await REGISTRY["email"]().send(event, config)).ok
    message = send.call_args.args[0]
    assert message["Subject"] == "[CRITICAL] prod1 — Backup health"
    assert {p.get_content_type() for p in message.iter_parts()} == {"text/plain", "text/html"}
    assert send.call_args.kwargs["start_tls"] is True and send.call_args.kwargs["use_tls"] is False
    await REGISTRY["email"]().send(event, {**config, "port": 465})
    assert send.call_args.kwargs["use_tls"] is True and send.call_args.kwargs["start_tls"] is False


@pytest.mark.asyncio
async def test_sms_rest_shape_and_length(event, requests):
    from urllib.parse import parse_qs
    event.instance = "long-instance" * 30
    config = {"account_sid": "AC" + "a" * 32, "auth_token": "secret", "from_number": "+15551234567", "to_numbers": ["+15557654321"]}
    assert (await REGISTRY["sms"]().send(event, config)).ok
    body = parse_qs(requests[0].content.decode())
    assert len(body["Body"][0]) <= 160 and body["Body"][0].endswith(event.dashboard_link)
    assert body["To"] == config["to_numbers"] and requests[0].headers["authorization"].startswith("Basic ")


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(429, 3), (500, 3), (400, 1)])
async def test_http_retries_sanitized_errors(status, expected, monkeypatch):
    monkeypatch.setattr(base.asyncio, "sleep", AsyncMock())
    client = AsyncMock()
    client.post.return_value = httpx.Response(status, text="secret", headers={"Retry-After": "1"})
    result = await base.post(client, "https://example.com/secret")
    assert not result.ok and client.post.await_count == expected
    assert "secret" not in result.message


@pytest.mark.asyncio
async def test_long_retry_after_is_deferred(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(base.asyncio, "sleep", sleep)
    client = AsyncMock()
    client.post.return_value = httpx.Response(429, headers={"Retry-After": "120"})
    result = await base.post(client, "https://example.com/secret")
    assert result.retryable and result.retry_after == 120 and client.post.await_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize("kind,config", [
    ("slack", {"webhook_url": "http://example.com"}),
    ("sms", {"account_sid": "AC" + "a" * 32, "auth_token": "secret", "from_number": "555", "to_numbers": ["+15551234567"]}),
    ("email", {"smtp_host": "smtp.example", "from_addr": "bad\r\nBcc: x", "to_addrs": ["ops@example.com"]}),
])
def test_invalid_channel_config(kind, config):
    with pytest.raises(ValueError):
        validate_config(kind, config)
