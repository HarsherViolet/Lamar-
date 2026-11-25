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



class FunctionLabels(unittest.TestCase):
    def test_title_head_decides(self):
        from _lamar.enrich import function
        cases = {
            ("Product Design Intern (Design Systems & AI Workflows)_ Jan 2027", ""): "Design",
            ("Senior Software Engineer, Data Platform", "Engineering"): "Engineering",
            ("Lead Integration Engineer, Orchestration Team", ""): "Engineering",
            ("Senior Data Scientist – Credit Risk", ""): "Data",
            ("Data Analyst", ""): "Data",
            ("Strategy Analyst", "Strategy"): "Business",
            ("AI Product Manager", ""): "Product",
            ("Research Scientist", ""): "Data",
            ("Counsel, Product Legal", ""): "Business",
            ("Senior Treasury Associate", ""): "Business",
            ("Intern - Retail Network Management", "Retail"): "Operations",
            ("Implementation Specialist", "Implementation"): "Operations",
            ("Merchant Sales Executive, GrabMart & GrabPay", ""): "Sales",
        }
        for (title, dept), want in cases.items():
            self.assertEqual(function(title, dept), want, title)



class Fields(unittest.TestCase):
    def test_education_roles(self):
        from _lamar.enrich import function
        for title in ["High School English Language and Literature Teacher", "Part-time Math Tutor",
                      "Montessori Teacher (English)", "Relief Preschool Teacher", "Lecturer, Computer Science",
                      "Team Lead of Curriculum Development and Teaching Management", "Data Science Instructor"]:
            self.assertEqual(function(title, ""), "Education", title)
        self.assertEqual(function("Principal Infrastructure Engineer, Cloud", ""), "Engineering")

    def test_singapore_typo_and_frontline_flag(self):
        from _lamar.enrich import to_role
        from _lamar.sources import raw
        co = {"name": "X", "ats": "lever", "about": ""}
        r = to_role(raw(title="Assistant Teacher", locations=["Singpaore"], url="u"), co)
        self.assertEqual((r["country"], r["fn"], r["frontline"]), ("SG", "Education", False))
        d = to_role(raw(title="Delivery Driver", locations=["Kuala Lumpur"], url="u"), co)
        self.assertTrue(d["frontline"])  # kept, but flagged

    def test_frontline_has_its_own_cap(self):
        from _lamar import pipeline
        from _lamar.sources import raw
        jobs = [raw(source_id=f"d{i}", title=f"Delivery Driver {i}", locations=["Kuala Lumpur"], url=f"u{i}",
                    posted="2026-11-20") for i in range(30)]
        jobs += [raw(source_id="a", title="Data Analyst", locations=["Kuala Lumpur"], url="ua", posted="2026-11-01")]
        with mock.patch.dict(sources.FETCHERS, {"lever": lambda t: jobs}):
            roles_, _ = pipeline.build([{"name": "Ninja", "ats": "lever", "token": "n"}], [])
        self.assertEqual(sum(r["frontline"] for r in roles_), pipeline.MAX_FRONTLINE_PER_COMPANY)
        self.assertIn("Data Analyst", [r["title"] for r in roles_])  # office role not crowded out


if __name__ == "__main__":
    unittest.main()
