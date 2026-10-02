"""Provider-neutral text generation for Data Eyes insights.

The dashboard speaks one small internal interface while each adapter handles
its vendor's transport.  No provider details leak into the frontend, Advisor,
or insight prompts.
"""

from __future__ import annotations

import json
import asyncio
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import AsyncIterator, Dict, List, Optional, Type, TypeVar

import httpx
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from .config import settings

logger = logging.getLogger(__name__)

Message = Dict[str, str]
StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class AIProviderError(RuntimeError):
    """A configured provider could not generate a response."""


@dataclass(frozen=True)
class AIStatus:
    provider: str
    provider_label: str
    configured: bool
    routine_model: str
    deep_model: str
    base_url: Optional[str] = None
    reason: Optional[str] = None

    def public_dict(self) -> dict:
        return asdict(self)


_DEFAULT_MODELS = {
    "anthropic": ("claude-haiku-4-5", "claude-opus-5"),
    "openai": ("gpt-5-mini", "gpt-5"),
    "local": ("llama3.2", "llama3.2"),
}


def _provider_name() -> str:
    name = settings.AI_PROVIDER.strip().lower()
    return "openai" if name == "chatgpt" else name


def _models(provider: str) -> tuple[str, str]:
    defaults = _DEFAULT_MODELS.get(provider, ("", ""))
    return (
        settings.AI_ROUTINE_MODEL or defaults[0],
        settings.AI_DEEP_MODEL or defaults[1],
    )


def get_ai_status() -> AIStatus:
    provider = _provider_name()
    routine_model, deep_model = _models(provider)
    if provider == "anthropic":
        configured = bool(settings.ANTHROPIC_API_KEY)
        return AIStatus(
            provider=provider,
            provider_label="Anthropic",
            configured=configured,
            routine_model=routine_model,
            deep_model=deep_model,
            reason=None if configured else "ANTHROPIC_API_KEY is not configured.",
        )
    if provider == "openai":
        configured = bool(settings.OPENAI_API_KEY)
        return AIStatus(
            provider=provider,
            provider_label="OpenAI",
            configured=configured,
            routine_model=routine_model,
            deep_model=deep_model,
            base_url=settings.OPENAI_BASE_URL,
            reason=None if configured else "OPENAI_API_KEY is not configured.",
        )
    if provider == "local":
        configured = bool(settings.LOCAL_AI_BASE_URL and routine_model and deep_model)
        return AIStatus(
            provider=provider,
            provider_label="Local AI",
            configured=configured,
            routine_model=routine_model,
            deep_model=deep_model,
            base_url=settings.LOCAL_AI_BASE_URL,
            reason=None if configured else "LOCAL_AI_BASE_URL and model names are required.",
        )
    return AIStatus(
        provider=provider,
        provider_label=provider or "Unknown",
        configured=False,
        routine_model=routine_model,
        deep_model=deep_model,
        reason="AI_PROVIDER must be anthropic, openai (or chatgpt), or local.",
    )


class AIProvider(ABC):
    def __init__(self, status: AIStatus):
        self.status = status

    def model(self, tier: str) -> str:
        return self.status.deep_model if tier == "deep" else self.status.routine_model

    @abstractmethod
    async def stream_text(
        self, *, system: str, messages: List[Message], tier: str, max_tokens: int
    ) -> AsyncIterator[str]:
        raise NotImplementedError

    @abstractmethod
    async def complete_text(
        self, *, system: str, messages: List[Message], tier: str, max_tokens: int
    ) -> str:
        raise NotImplementedError

    async def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        output_type: Type[StructuredModel],
        tier: str = "deep",
        max_tokens: int = 4096,
    ) -> StructuredModel:
        schema = json.dumps(output_type.model_json_schema(), separators=(",", ":"))
        json_prompt = (
            f"{prompt}\n\nReturn only one JSON object matching this JSON Schema. "
            f"Do not wrap it in Markdown fences.\n{schema}"
        )
        raw = await self.complete_text(
            system=system,
            messages=[{"role": "user", "content": json_prompt}],
            tier=tier,
            max_tokens=max_tokens,
        )
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end < start:
            raise AIProviderError("The AI provider did not return a JSON object.")
        try:
            return output_type.model_validate_json(raw[start : end + 1])
        except Exception as exc:
            raise AIProviderError("The AI provider returned invalid structured output.") from exc


class AnthropicProvider(AIProvider):
    def __init__(self, status: AIStatus):
        super().__init__(status)
        self.client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def stream_text(
        self, *, system: str, messages: List[Message], tier: str, max_tokens: int
    ) -> AsyncIterator[str]:
        try:
            async with self.client.messages.stream(
                model=self.model(tier),
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            raise AIProviderError("Anthropic generation failed.") from exc

    async def complete_text(
        self, *, system: str, messages: List[Message], tier: str, max_tokens: int
    ) -> str:
        try:
            response = await self.client.messages.create(
                model=self.model(tier),
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return "".join(block.text for block in response.content if block.type == "text")
        except Exception as exc:
            raise AIProviderError("Anthropic generation failed.") from exc


class OpenAICompatibleProvider(AIProvider):
    """Chat Completions adapter used by OpenAI and local compatible servers."""

    def __init__(self, status: AIStatus, *, api_key: Optional[str], local: bool):
        super().__init__(status)
        self.api_key = api_key
        self.local = local
        self.endpoint = f"{status.base_url.rstrip('/')}/chat/completions"

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _http_error(self, exc: httpx.HTTPStatusError) -> AIProviderError:
        status_code = exc.response.status_code
        error_code = None
        try:
            payload = exc.response.json()
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            error_code = error.get("code") if isinstance(error, dict) else None
        except Exception:
            pass
        if error_code == "missing_scope":
            return AIProviderError(
                f"{self.status.provider_label} denied model generation (missing_scope). "
                "Ask your OpenAI project administrator to enable Model capabilities: Request "
                "for the API key and its project role, or configure an authorized key."
            )
        if status_code == 401:
            return AIProviderError(
                f"{self.status.provider_label} rejected the API key (HTTP 401)."
            )
        return AIProviderError(
            f"{self.status.provider_label} returned HTTP {status_code}"
            + (f" ({error_code})." if error_code else ".")
        )

    def _body(self, *, system: str, messages: List[Message], tier: str, max_tokens: int, stream: bool) -> dict:
        body = {
            "model": self.model(tier),
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": stream,
        }
        body["max_tokens" if self.local else "max_completion_tokens"] = max_tokens
        return body

    async def stream_text(
        self, *, system: str, messages: List[Message], tier: str, max_tokens: int
    ) -> AsyncIterator[str]:
        try:
            timeout = httpx.Timeout(settings.AI_REQUEST_TIMEOUT_SECONDS)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    self.endpoint,
                    headers=self._headers(),
                    json=self._body(system=system, messages=messages, tier=tier, max_tokens=max_tokens, stream=True),
                ) as response:
                    if response.is_error:
                        # Error bodies are not buffered automatically in streaming
                        # mode; read this small payload so the sanitized provider
                        # error code (for example missing_scope) can be classified.
                        await response.aread()
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload or payload == "[DONE]":
                            continue
                        data = json.loads(payload)
                        text = data.get("choices", [{}])[0].get("delta", {}).get("content")
                        if text:
                            yield text
        except httpx.HTTPStatusError as exc:
            raise self._http_error(exc) from exc
        except Exception as exc:
            raise AIProviderError(f"{self.status.provider_label} generation failed.") from exc

    async def complete_text(
        self, *, system: str, messages: List[Message], tier: str, max_tokens: int
    ) -> str:
        try:
            timeout = httpx.Timeout(settings.AI_REQUEST_TIMEOUT_SECONDS)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers=self._headers(),
                    json=self._body(system=system, messages=messages, tier=tier, max_tokens=max_tokens, stream=False),
                )
                response.raise_for_status()
                content = response.json().get("choices", [{}])[0].get("message", {}).get("content")
                if not isinstance(content, str) or not content:
                    raise AIProviderError("The AI provider returned no text.")
                return content
        except AIProviderError:
            raise
        except httpx.HTTPStatusError as exc:
            raise self._http_error(exc) from exc
        except Exception as exc:
            raise AIProviderError(f"{self.status.provider_label} generation failed.") from exc


_ai_slots = None


class LimitedProvider(AIProvider):
    """Apply quotas to foreground and background calls, including full streams."""
    def __init__(self, provider):
        super().__init__(provider.status)
        self.provider = provider

    async def _acquire(self, quota_scope: str = "interactive"):
        from .security_limits import quota
        global _ai_slots
        if _ai_slots is None:
            _ai_slots = asyncio.Semaphore(settings.AI_MAX_CONCURRENT_REQUESTS)
        # Take the concurrency slot first so a busy provider doesn't burn
        # hourly quota on requests that never run. Background sweeps have their
        # own bucket so they can't exhaust the budget for Ask/Advisor/Explain.
        try:
            await asyncio.wait_for(_ai_slots.acquire(), timeout=1)
        except Exception as exc:
            raise AIProviderError("AI request limit reached or quota service unavailable; retry later") from exc
        try:
            if quota_scope == "background":
                await quota("ai-global-hour-background", "all", 120, 3600)
            else:
                await quota("ai-global-hour", "all", 300, 3600)
        except BaseException as exc:
            _ai_slots.release()
            if isinstance(exc, Exception):
                raise AIProviderError("AI request limit reached or quota service unavailable; retry later") from exc
            raise
        return _ai_slots

    def _validate(self, system, messages):
        size = len(system) + sum(len(item.get("content", "")) for item in messages)
        if len(messages) > 20 or size > 32000:
            raise AIProviderError("AI input exceeds the configured request size limit")

    async def stream_text(self, *, system, messages, tier, max_tokens, quota_scope="interactive"):
        self._validate(system, messages)
        slots = await self._acquire(quota_scope)
        stream = self.provider.stream_text(system=system, messages=messages, tier=tier, max_tokens=max_tokens)
        deadline = time.monotonic() + settings.AI_REQUEST_TIMEOUT_SECONDS
        try:
            while True:
                try:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise asyncio.TimeoutError
                    chunk = await asyncio.wait_for(stream.__anext__(), timeout=remaining)
                except StopAsyncIteration:
                    break
                yield chunk
        except asyncio.TimeoutError:
            raise AIProviderError("AI request timed out") from None
        finally:
            try:
                await stream.aclose()
            finally:
                slots.release()

    async def complete_text(self, *, system, messages, tier, max_tokens, quota_scope="interactive"):
        self._validate(system, messages)
        slots = await self._acquire(quota_scope)
        try:
            return await asyncio.wait_for(self.provider.complete_text(
                system=system, messages=messages, tier=tier, max_tokens=max_tokens),
                timeout=settings.AI_REQUEST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            raise AIProviderError("AI request timed out") from None
        finally:
            slots.release()


@lru_cache(maxsize=1)
def get_ai_provider() -> Optional[AIProvider]:
    status = get_ai_status()
    if not status.configured:
        return None
    if status.provider == "anthropic":
        return LimitedProvider(AnthropicProvider(status))
    if status.provider == "openai":
        return LimitedProvider(OpenAICompatibleProvider(status, api_key=settings.OPENAI_API_KEY, local=False))
    if status.provider == "local":
        return LimitedProvider(OpenAICompatibleProvider(status, api_key=settings.LOCAL_AI_API_KEY, local=True))
    return None
