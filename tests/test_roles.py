"""Offline tests for GET /api/roles. Run: python -m unittest discover -s tests -t ."""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
import roles  # noqa: E402
from _lamar import sources  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def fake_fetchers():
    def make(ats):
        def f(token):
            p = FIX / f"{ats}_{token}.json"
            if not p.exists():
                raise sources.FeedError(f"HTTP 404 for {token}")
            data = json.loads(p.read_text())
            fn = getattr(sources, f"parse_{ats}")
            return fn(data, token) if ats == "smartrecruiters" else fn(data)
        return f
    return {k: make(k) for k in sources.FETCHERS}


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


class Roles(unittest.TestCase):
    def test_roles_endpoint(self):
        with mock.patch.dict(sources.FETCHERS, fake_fetchers()):
            status, headers, body = call(roles.handler, "GET")
        self.assertEqual(status, 200)
        self.assertIn("s-maxage=21600", headers["Cache-Control"])
        self.assertGreaterEqual(len(body["roles"]), 8)
        self.assertTrue(all(r["first_seen"] == r["posted"] for r in body["roles"]))
        self.assertIn("Xendit", body["meta"]["failures"])  # unverified guess fails cleanly
        dates = [r["posted"] for r in body["roles"]]
        self.assertEqual(dates, sorted(dates, reverse=True))


if __name__ == "__main__":
    unittest.main()
