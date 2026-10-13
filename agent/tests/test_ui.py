"""Exercise the chat UI without provider credentials or a running API."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from streamlit.testing.v1 import AppTest


UI = Path(__file__).resolve().parents[1] / "app" / "ui.py"
STATUS = {"provider_label": "Test provider", "model": "test-model",
          "configured": True, "monitoring_configured": True, "reason": None}


def response(events, status_code=200):
    body = "".join(f"event: {kind}\ndata: {json.dumps(data)}\n\n" for kind, data in events)
    return httpx.Response(status_code, text=body, request=httpx.Request("POST", "http://agent/api/agent/ask"))


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.get = patch("httpx.get", return_value=httpx.Response(
            200, json=STATUS, request=httpx.Request("GET", "http://agent/api/agent/status"))).start()
        self.stream = patch("httpx.stream").start()
        self.addCleanup(patch.stopall)

    def stream_events(self, events, status_code=200):
        self.stream.return_value.__enter__.return_value = response(events, status_code)

    def test_chat_progress_history_and_clear(self):
        self.stream_events([("status", {"text": "Reading metrics"}),
                            ("text", {"text": "Fleet is healthy."}),
                            ("text", {"text": "\n\nNo blocking."}), ("done", {})])
        app = AppTest.from_file(str(UI)).run()
        self.assertFalse(app.exception)
        app.chat_input[0].set_value("How is the fleet?").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.messages[-1]["content"], "Fleet is healthy.\n\nNo blocking.")
        self.assertEqual(app.status[0].state, "complete")
        app.chat_input[0].set_value("Any blocking?").run()
        self.assertEqual(len(self.stream.call_args.kwargs["json"]["messages"]), 3)
        app.sidebar.button[0].click().run()
        self.assertEqual(app.session_state.messages, [])

    def test_unconfigured_and_unreachable(self):
        self.get.return_value = httpx.Response(200, json={**STATUS, "configured": False, "reason": "Missing key"},
                                              request=httpx.Request("GET", "http://agent"))
        app = AppTest.from_file(str(UI)).run()
        self.assertTrue(app.chat_input[0].disabled)
        self.assertEqual(app.warning[0].value, "Missing key")
        self.get.side_effect = httpx.ConnectError("offline")
        app.sidebar.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.chat_input[0].disabled)
        self.assertIn("Cannot reach", app.error[0].value)

    def test_failed_answers_are_visible_and_excluded_from_context(self):
        self.stream_events([("text", {"text": "Partial"}), ("error", {"error": "Provider failed"}), ("done", {})])
        app = AppTest.from_file(str(UI)).run()
        app.chat_input[0].set_value("Health?").run()
        self.assertEqual(app.error[0].value, "Provider failed")
        self.assertEqual(app.status[0].state, "error")
        self.stream_events([("text", {"text": "Healthy"}), ("done", {})])
        app.chat_input[0].set_value("Try again").run()
        self.assertEqual(self.stream.call_args.kwargs["json"]["messages"], [{"role": "user", "content": "Try again"}])

    def test_busy_and_interrupted_stream(self):
        for frames, code, expected in [([], 429, "busy"), ([("text", {"text": "Partial"})], 200, "connection ended")]:
            with self.subTest(code=code):
                self.stream_events(frames, code)
                app = AppTest.from_file(str(UI)).run()
                app.chat_input[0].set_value("Health?").run()
                self.assertFalse(app.exception)
                self.assertIn(expected, app.error[0].value)

    def test_context_stays_within_api_limits(self):
        self.stream_events([("text", {"text": "Healthy"}), ("done", {})])
        app = AppTest.from_file(str(UI)).run()
        app.session_state.messages = [m for _ in range(25) for m in (
            {"role": "user", "content": "Health?"}, {"role": "assistant", "content": "x" * 9000})]
        app.chat_input[0].set_value("Now?").run()
        sent = self.stream.call_args.kwargs["json"]["messages"]
        self.assertEqual(len(sent), 39)
        self.assertTrue(all(len(m["content"]) <= 8000 for m in sent))
        self.assertEqual(sent[0]["role"], "user")


if __name__ == "__main__":
    unittest.main()
