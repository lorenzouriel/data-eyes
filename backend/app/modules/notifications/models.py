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
    # transition: a state alert changed severity; event: a one-off occurrence
    # (deadlock, failed job); reminder: still open after the rule's re-notify
    # or escalation delay; digest: the daily DB checklist.
    kind: Literal["transition", "event", "reminder", "digest"] = "transition"
    instance: str
    category: str
    title: str | None = None
    old_severity: Severity | None
    new_severity: Severity
    metric_value: float | None = None
    detail: str | None = None
    open_since: datetime | None = None
    dashboard_link: str
    timestamp: datetime
    # Grouped events retain all original values and transitions.
    grouped: list["NotificationEvent"] = Field(default_factory=list)

    @property
    def label(self) -> str:
        return self.title or self.category

    def _line(self) -> str:
        if self.kind == "event":
            text = f"{self.label}: {self.new_severity} event"
        elif self.kind == "reminder":
            since = f" since {self.open_since:%Y-%m-%d %H:%M} UTC" if self.open_since else ""
            text = f"{self.label}: still {self.new_severity}{since}"
        else:
            text = f"{self.label}: {self.old_severity or 'INITIAL'} → {self.new_severity}"
        if self.metric_value is not None:
            text += f" (value: {self.metric_value:g})"
        if self.detail:
            text += "\n  " + self.detail.replace("\n", "\n  ")
        return text

    @property
    def description(self) -> str:
        if self.kind == "digest":
            return f"{self.label}\n{self.detail or ''}".strip()
        return "\n".join(e._line() for e in self.grouped or [self])


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
    # "Alert without clear": repeat while a state alert stays open.
    renotify_seconds: int | None = Field(default=None, ge=300, le=604800)
    # Escalation: stay silent on the transition and notify only once the
    # alert has been open this long (for example, a manager's channel).
    escalate_after_seconds: int | None = Field(default=None, ge=60, le=604800)

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
    from app.core.config import settings
    return NotificationEvent(instance="Data Eyes test", category="Notification test",
                             old_severity="OK", new_severity="CRITICAL", metric_value=1,
                             dashboard_link=settings.PUBLIC_BASE_URL.rstrip("/") + "/",
                             timestamp=datetime.now(timezone.utc))
