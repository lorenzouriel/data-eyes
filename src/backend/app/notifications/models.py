"""Validated notification configuration and transport-neutral delivery models."""
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

Severity = Literal["OK", "WARNING", "CRITICAL", "UNKNOWN"]
ChannelType = Literal["slack", "teams", "email", "sms"]
SECRET_FIELDS = {"webhook_url", "password", "auth_token", "account_sid", "username"}
MASK = "********"


class NotificationEvent(BaseModel):
    instance: str
    category: str
    old_severity: Severity | None
    new_severity: Severity
    metric_value: float | None = None
    dashboard_link: str
    timestamp: datetime
    # Grouped events retain all original values and transitions.
    grouped: list["NotificationEvent"] = Field(default_factory=list)

    @property
    def description(self) -> str:
        events = self.grouped or [self]
        return "\n".join(
            f"{e.category}: {e.old_severity or 'INITIAL'} → {e.new_severity}"
            + (f" (value: {e.metric_value:g})" if e.metric_value is not None else "")
            for e in events
        )


class DeliveryResult(BaseModel):
    ok: bool
    message: str = "Delivered"
    retryable: bool = False
    retry_after: float = 1
    attempts: int = 1


class ChannelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    type: ChannelType
    enabled: bool = True
    config: dict[str, Any]


class RuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    channel_id: int = Field(gt=0)
    enabled: bool = True
    instance: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=200)
    severities: list[Literal["WARNING", "CRITICAL", "UNKNOWN"]] = Field(default_factory=lambda: ["CRITICAL"], min_length=1)
    recovery: bool = False
    cooldown_seconds: int | None = Field(default=None, ge=0, le=604800)
    quiet_start: int | None = Field(default=None, ge=0, le=23)
    quiet_end: int | None = Field(default=None, ge=0, le=23)
    group_by_instance: bool = False

    @model_validator(mode="after")
    def quiet_hours_pair(self):
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError("Both quiet-hour endpoints are required (UTC)")
        if self.quiet_start is not None and self.quiet_start == self.quiet_end:
            raise ValueError("Quiet-hour endpoints must differ")
        return self


def validate_config(kind: ChannelType, config: dict) -> dict:
    """Reject unknown fields and malformed destinations without echoing secrets."""
    import re

    allowed = {
        "slack": {"webhook_url", "channel", "mention"},
        "teams": {"webhook_url"},
        "email": {"smtp_host", "port", "username", "password", "use_tls", "from_addr", "to_addrs"},
        "sms": {"provider", "account_sid", "auth_token", "from_number", "to_numbers"},
    }[kind]
    if set(config) - allowed:
        raise ValueError("Unknown channel configuration field")

    def string(key, required=True):
        value = config.get(key, "")
        if not isinstance(value, str) or len(value) > 4096 or "\r" in value or "\n" in value:
            raise ValueError(f"Invalid {key}")
        if required and (not value.strip() or value == MASK):
            raise ValueError(f"{key} is required")
        return value

    if kind in ("slack", "teams"):
        url = urlsplit(string("webhook_url"))
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
            raise ValueError("Webhook must be an HTTPS URL without user credentials or fragment")
        if kind == "slack":
            string("channel", False)
            string("mention", False)
    elif kind == "email":
        string("smtp_host")
        string("username", False)
        string("password", False)
        port = config.get("port", 587)
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("Invalid SMTP port")
        if not isinstance(config.get("use_tls", True), bool):
            raise ValueError("Invalid use_tls")
        addresses = config.get("to_addrs")
        if not isinstance(addresses, list) or not 1 <= len(addresses) <= 50:
            raise ValueError("Provide 1–50 recipient addresses")
        for address in [string("from_addr"), *addresses]:
            if not isinstance(address, str) or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", address):
                raise ValueError("Invalid email address")
        config = {"port": 587, "use_tls": True, **config}
    else:
        if config.get("provider", "twilio") != "twilio":
            raise ValueError("Only Twilio is supported")
        if not re.fullmatch(r"AC[0-9a-fA-F]{32}", string("account_sid")):
            raise ValueError("Invalid Twilio account SID")
        string("auth_token")
        numbers = config.get("to_numbers")
        if not isinstance(numbers, list) or not 1 <= len(numbers) <= 20:
            raise ValueError("Provide 1–20 recipient numbers")
        for number in [string("from_number"), *numbers]:
            if not isinstance(number, str) or not re.fullmatch(r"\+[1-9]\d{1,14}", number):
                raise ValueError("Phone numbers must use E.164, such as +15551234567")
        config = {"provider": "twilio", **config}
    return config


def test_event() -> NotificationEvent:
    from ..config import settings
    return NotificationEvent(instance="Data Eyes test", category="Notification test",
                             old_severity="OK", new_severity="CRITICAL", metric_value=1,
                             dashboard_link=settings.PUBLIC_BASE_URL.rstrip("/") + "/",
                             timestamp=datetime.now(timezone.utc))
