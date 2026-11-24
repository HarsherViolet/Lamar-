"""Fetchers for public applicant-tracking-system (ATS) job feeds.

Each fetcher returns a list of RawJob dicts with the same keys, so the rest
of the pipeline never needs to know which system a job came from.
These are the public, documented feeds companies use to embed job boards
on their own sites; no login or scraping of HTML is involved.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape

USER_AGENT = "LamarJobBot/1.0 (+https://github.com/; student project)"
TIMEOUT = 25


class FeedError(Exception):
    """A company's feed could not be read (bad token, outage, format change)."""


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise FeedError(f"HTTP {e.code} from {url}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise FeedError(f"{type(e).__name__} from {url}: {e}") from e


def strip_html(s: str | None) -> str:
    s = unescape(unescape(s or ""))  # Greenhouse double-escapes content
    s = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def to_date(v) -> str:
    """Normalise ISO strings and epoch milliseconds to YYYY-MM-DD ('' if unknown)."""
    if v in (None, ""):
        return ""
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v))
    return m.group(1) if m else ""


def raw(**kw) -> dict:
    base = dict(source_id="", title="", locations=[], department="", employment="",
                workplace="", posted="", url="", description="", salary="")
    base.update(kw)
    base["locations"] = [l for l in base["locations"] if l]
    return base


# ---------------- Greenhouse ----------------
def parse_greenhouse(data: dict) -> list[dict]:
    out = []
    for j in data.get("jobs", []):
        locs = [(j.get("location") or {}).get("name", "")]
        locs += [o.get("name", "") for o in j.get("offices", []) or []]
        out.append(raw(
            source_id=str(j.get("id", "")),
            title=j.get("title", ""),
            locations=locs,
            department=", ".join(d.get("name", "") for d in j.get("departments", []) or []),
            posted=to_date(j.get("first_published") or j.get("updated_at")),
            url=j.get("absolute_url", ""),
            description=strip_html(j.get("content")),
        ))
    return out


def fetch_greenhouse(token: str) -> list[dict]:
    t = urllib.parse.quote(token)
    return parse_greenhouse(get_json(f"https://boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true"))


# ---------------- Lever ----------------
def parse_lever(data: list) -> list[dict]:
    out = []
    for j in data if isinstance(data, list) else []:
        c = j.get("categories") or {}
        locs = c.get("allLocations") or [c.get("location", "")]
        sal = j.get("salaryRange") or {}
        salary = ""
        if sal.get("min") and sal.get("max"):
            salary = f"{sal.get('currency', '')} {sal['min']:,}–{sal['max']:,} {sal.get('interval', '')}".strip()
        out.append(raw(
            source_id=str(j.get("id", "")),
            title=j.get("text", ""),
            locations=locs,
            department=" / ".join(x for x in (c.get("department"), c.get("team")) if x),
            employment=c.get("commitment", ""),
            workplace=j.get("workplaceType", ""),
            posted=to_date(j.get("createdAt")),
            url=j.get("hostedUrl", ""),
            description=j.get("descriptionPlain") or strip_html(j.get("description")),
            salary=salary,
        ))
    return out


def fetch_lever(token: str) -> list[dict]:
    t = urllib.parse.quote(token)
    return parse_lever(get_json(f"https://api.lever.co/v0/postings/{t}?mode=json"))


# ---------------- Ashby ----------------
def parse_ashby(data: dict) -> list[dict]:
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location", "")] + [
            (s or {}).get("location", "") for s in j.get("secondaryLocations", []) or []]
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        out.append(raw(
            source_id=str(j.get("id", "")),
            title=j.get("title", ""),
            locations=locs,
            department=" / ".join(x for x in (j.get("department"), j.get("team")) if x),
            employment=j.get("employmentType", ""),
            workplace="Remote" if j.get("isRemote") else (j.get("workplaceType") or ""),
            posted=to_date(j.get("publishedAt")),
            url=j.get("jobUrl", ""),
            description=j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")),
            salary=comp,
        ))
    return out


def fetch_ashby(token: str) -> list[dict]:
    t = urllib.parse.quote(token)
    return parse_ashby(get_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{t}?includeCompensation=true"))


# ---------------- Workable ----------------
def parse_workable(data: dict) -> list[dict]:
    out = []
    for j in data.get("jobs", []):
        locs = []
        for l in j.get("locations", []) or []:
            locs.append(", ".join(x for x in (l.get("city"), l.get("country")) if x))
        if not locs:
            locs = [", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)]
        out.append(raw(
            source_id=str(j.get("shortcode", "")),
            title=j.get("title", ""),
            locations=locs,
            department=j.get("department", "") or "",
            employment=j.get("employment_type", "") or "",
            workplace="Remote" if j.get("telecommuting") else "",
            posted=to_date(j.get("published_on") or j.get("created_at")),
            url=j.get("url") or j.get("shortlink") or "",
            description=strip_html(j.get("description")),
        ))
    return out


def fetch_workable(token: str) -> list[dict]:
    t = urllib.parse.quote(token)
    return parse_workable(get_json(f"https://apply.workable.com/api/v1/widget/accounts/{t}?details=true"))


# ---------------- SmartRecruiters ----------------
def parse_smartrecruiters(data: dict, token: str) -> list[dict]:
    out = []
    for j in data.get("content", []):
        loc = j.get("location") or {}
        place = ", ".join(x for x in (loc.get("city"), loc.get("country", "").upper()) if x)
        pid = str(j.get("id", ""))
        out.append(raw(
            source_id=pid,
            title=j.get("name", ""),
            locations=[place],
            department=(j.get("department") or {}).get("label", ""),
            employment=(j.get("typeOfEmployment") or {}).get("label", ""),
            workplace="Remote" if loc.get("remote") else ("Hybrid" if loc.get("hybrid") else ""),
            posted=to_date(j.get("releasedDate")),
            url=f"https://jobs.smartrecruiters.com/{token}/{pid}",
            description=" ".join(x for x in ((j.get("experienceLevel") or {}).get("label", ""),
                                             (j.get("function") or {}).get("label", "")) if x),
        ))
    return out


def fetch_smartrecruiters(token: str) -> list[dict]:
    t = urllib.parse.quote(token)
    jobs, offset = [], 0
    while True:  # paginated, 100 per page
        data = get_json(f"https://api.smartrecruiters.com/v1/companies/{t}/postings?limit=100&offset={offset}")
        page = parse_smartrecruiters(data, token)
        jobs += page
        offset += 100
        if not page or offset >= int(data.get("totalFound", 0)) or offset >= 1000:
            return jobs


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workable": fetch_workable,
    "smartrecruiters": fetch_smartrecruiters,
}
