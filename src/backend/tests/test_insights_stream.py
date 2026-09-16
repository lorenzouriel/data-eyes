import unittest

from app.ai_provider import AIProviderError
from app.routers.insights import _sse


async def failing_stream():
    raise AIProviderError("OpenAI rejected the API key (HTTP 401).")
    yield "unreachable"


class InsightStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_failure_is_sent_as_sse_error(self):
        frames = [frame async for frame in _sse(failing_stream())]
        self.assertEqual(len(frames), 1)
        self.assertIn("event: error", frames[0])
        self.assertIn("HTTP 401", frames[0])


if __name__ == "__main__":
    unittest.main()
