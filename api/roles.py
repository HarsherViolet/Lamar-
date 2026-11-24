"""GET /api/roles: Malaysia and Singapore startup roles, read live from public job feeds.

Vercel's edge cache keeps the answer for 6 hours, so the feeds are read at most
about 4 times a day however often the app is opened. No database is needed.
"""
import json
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _lamar import sources  # noqa: E402
from _lamar.pipeline import build, load_companies  # noqa: E402

sources.TIMEOUT = 9  # a slow feed must not hold up the rest
COMPANIES = Path(__file__).parent / "_lamar" / "companies.json"


def collect():
    roles, meta = build(load_companies(COMPANIES), [])
    # No stored history here, so "first seen" is the posting date: New = posted in the last few days.
    for r in roles:
        r["first_seen"] = r.get("posted") or r["first_seen"]
    roles.sort(key=lambda r: r.get("posted") or "", reverse=True)
    meta["new_today"] = None
    meta["closed_since_last_run"] = None
    return {"roles": roles, "meta": meta}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body, status = collect(), 200
            cache = "public, s-maxage=21600, stale-while-revalidate=86400"
        except Exception as e:  # never cache a failure
            body, status = {"roles": [], "meta": {"error": f"{type(e).__name__}: {e}",
                            "updated_at": datetime.now(timezone.utc).isoformat()}}, 500
            cache = "no-store"
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
