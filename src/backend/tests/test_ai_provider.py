import unittest
from typing import AsyncIterator, List
from unittest.mock import patch

import httpx

from pydantic import BaseModel

from app.ai_provider import (
    AIProvider,
    AIStatus,
    OpenAICompatibleProvider,
    get_ai_provider,
    get_ai_status,
)
from app.config import settings


class ExampleOutput(BaseModel):
    answer: str


class FakeProvider(AIProvider):
    async def stream_text(
        self, *, system: str, messages: List[dict], tier: str, max_tokens: int
    ) -> AsyncIterator[str]:
        yield "ok"

    async def complete_text(
        self, *, system: str, messages: List[dict], tier: str, max_tokens: int
    ) -> str:
        return '```json\n{"answer":"portable"}\n```'


class AIStatusTests(unittest.TestCase):
    def tearDown(self):
        get_ai_provider.cache_clear()

    def test_chatgpt_alias_uses_openai(self):
        with patch.object(settings, "AI_PROVIDER", "chatgpt"), patch.object(
            settings, "OPENAI_API_KEY", "test-key"
        ):
            status = get_ai_status()
        self.assertEqual(status.provider, "openai")
        self.assertEqual(status.provider_label, "OpenAI")
        self.assertTrue(status.configured)

    def test_local_provider_needs_no_key(self):
        with (
            patch.object(settings, "AI_PROVIDER", "local"),
            patch.object(settings, "AI_ROUTINE_MODEL", "local-small"),
            patch.object(settings, "AI_DEEP_MODEL", "local-large"),
            patch.object(settings, "LOCAL_AI_API_KEY", None),
        ):
            status = get_ai_status()
        self.assertTrue(status.configured)
        self.assertEqual(status.routine_model, "local-small")
        self.assertEqual(status.deep_model, "local-large")

    def test_openai_missing_scope_error_is_actionable(self):
        status = AIStatus(
            "openai", "OpenAI", True, "small", "large", "https://api.openai.com/v1"
        )
        provider = OpenAICompatibleProvider(status, api_key="test", local=False)
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        response = httpx.Response(
            401,
            request=request,
            json={"error": {"type": "invalid_request_error", "code": "missing_scope"}},
        )
        error = provider._http_error(
            httpx.HTTPStatusError("unauthorized", request=request, response=response)
        )
        self.assertIn("lacks model-completion permission", str(error))


class StructuredOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_output_is_validated_provider_neutrally(self):
        provider = FakeProvider(
            AIStatus("local", "Local AI", True, "small", "large")
        )
        result = await provider.complete_structured(
            system="test", prompt="answer", output_type=ExampleOutput
        )
        self.assertEqual(result.answer, "portable")


if __name__ == "__main__":
    unittest.main()
