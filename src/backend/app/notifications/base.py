"""Async delivery contract. Provider errors must never expose configuration."""
import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from .models import DeliveryResult, NotificationEvent, test_event

# httpx INFO request logs include the full credential-bearing webhook URL.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class Notifier(ABC):
    @abstractmethod
    async def send(self, event: NotificationEvent, config: dict) -> DeliveryResult:
        """Send an event; return only sanitized errors."""

    async def test(self, config: dict) -> DeliveryResult:
        return await self.send(test_event(), config)


async def post(client: httpx.AsyncClient, url: str, **kwargs) -> DeliveryResult:
    """Bounded HTTP retry, including Retry-After; no response bodies or URLs in logs."""
    for attempt in range(1, 4):
        try:
            response = await client.post(url, **kwargs)
            if 200 <= response.status_code < 300:
                return DeliveryResult(ok=True, attempts=attempt)
            retryable = response.status_code == 429 or response.status_code >= 500
            delay = float(attempt)
            header = response.headers.get("Retry-After")
            if header:
                try:
                    delay = float(header)
                except ValueError:
                    try:
                        delay = (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        pass
            result = DeliveryResult(ok=False, message=f"Provider HTTP {response.status_code}",
                                    retryable=retryable, retry_after=max(1, min(delay, 3600)), attempts=attempt)
        except httpx.HTTPError:
            result = DeliveryResult(ok=False, message="Provider connection failed", retryable=True, attempts=attempt)
        if not result.retryable or attempt == 3 or result.retry_after > 5:
            return result
        await asyncio.sleep(result.retry_after)
    return result
