"""Offline tests for POST /api/ai. Run: python -m unittest discover -s tests -t ."""
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
import ai  # noqa: E402


def call(handler_cls, method, body=None, headers=None):
    raw = json.dumps(body).encode() if body is not None else b""
    h = handler_cls.__new__(handler_cls)
    h.rfile, h.wfile = io.BytesIO(raw), io.BytesIO()
    h.headers = {"Content-Length": str(len(raw)), **(headers or {})}
    sent = {}
    h.send_response = lambda s: sent.__setitem__("status", s)
    h.send_header = lambda k, v: sent.setdefault("headers", {}).__setitem__(k, v)
    h.end_headers = lambda: None
    getattr(h, f"do_{method}")()
    return sent["status"], sent["headers"], json.loads(h.wfile.getvalue())


class AI(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_no_keys(self):
        r = ai.complete("hi")
        self.assertEqual(r["code"], "not_configured")

    def test_gemini_json(self):
        os.environ["GEMINI_API_KEY"] = "k"
        reply = {"candidates": [{"content": {"parts": [{"text": '{"a":1}'}]}}]}
        with mock.patch.object(ai, "post_json", return_value=reply) as pj:
            r = ai.complete("x", True, [{"mime": "image/png", "data": "AAA"}])
        self.assertEqual((r["text"], r["provider"]), ('{"a":1}', "gemini"))
        url, payload, hdrs = pj.call_args[0]
        self.assertIn("gemini-flash-latest:generateContent", url)
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(payload["contents"][0]["parts"][1]["inline_data"]["data"], "AAA")
        self.assertEqual(hdrs, {"x-goog-api-key": "k"})

    def test_falls_back_to_groq_and_unwraps_list(self):
        os.environ.update(GEMINI_API_KEY="g", GROQ_API_KEY="q")
        def fake(url, payload, headers, timeout=55):
            if "googleapis" in url:
                raise ai.ProviderError("rate_limited", "HTTP 429")
            return {"choices": [{"message": {"content": '{"items":[{"id":"x","score":80}]}'}}]}
        with mock.patch.object(ai, "post_json", side_effect=fake):
            r = ai.complete("rank", True)
        self.assertEqual(r["provider"], "groq")
        self.assertEqual(json.loads(r["text"]), [{"id": "x", "score": 80}])

    def test_rate_limited_everywhere(self):
        os.environ.update(GEMINI_API_KEY="g")
        with mock.patch.object(ai, "post_json", side_effect=ai.ProviderError("rate_limited", "429")):
            r = ai.complete("x")
        self.assertEqual(r["code"], "rate_limited")

    def test_openai_compatible(self):
        os.environ.update(OPENAI_API_KEY="o", OPENAI_MODEL="some-model", OPENAI_BASE_URL="https://example.com/v1/")
        with mock.patch.object(ai, "post_json", return_value={"choices": [{"message": {"content": "hello"}}]}) as pj:
            r = ai.complete("x")
        self.assertEqual((r["text"], r["provider"]), ("hello", "openai"))
        self.assertEqual(pj.call_args[0][0], "https://example.com/v1/chat/completions")

    def test_handler_passcode_and_status(self):
        os.environ.update(LAMAR_PASSCODE="secret", GEMINI_API_KEY="g")
        s, _, b = call(ai.handler, "POST", {"prompt": "x"})
        self.assertEqual((s, b["code"]), (401, "passcode"))
        reply = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        with mock.patch.object(ai, "post_json", return_value=reply):
            s, h, b = call(ai.handler, "POST", {"prompt": "x"}, {"x-lamar-passcode": "secret"})
        self.assertEqual((s, b["text"], h["Cache-Control"]), (200, "ok", "no-store"))


if __name__ == "__main__":
    unittest.main()
