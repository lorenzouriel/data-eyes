"""Provider-neutral text generation for Data Eyes insights.

The dashboard speaks one small internal interface while each adapter handles
its vendor's transport.  No provider details leak into the frontend, Advisor,
or insight prompts.
"""

from __future__ import annotations

import json
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
                f"{self.status.provider_label} API key lacks model-completion permission (missing_scope)."
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


@lru_cache(maxsize=1)
def get_ai_provider() -> Optional[AIProvider]:
    status = get_ai_status()
    if not status.configured:
        return None
    if status.provider == "anthropic":
        return AnthropicProvider(status)
    if status.provider == "openai":
        return OpenAICompatibleProvider(status, api_key=settings.OPENAI_API_KEY, local=False)
    if status.provider == "local":
        return OpenAICompatibleProvider(status, api_key=settings.LOCAL_AI_API_KEY, local=True)
    return None
