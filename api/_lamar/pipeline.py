"""Run every company feed, keep MY/SG/APAC-remote roles, and write data/roles.json.

    python -m lamar.pipeline                 # live run
    python -m lamar.pipeline --fixtures tests/fixtures   # offline run from saved feeds
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import sources
from .enrich import to_role

ROOT = Path(__file__).resolve().parent.parent
MAX_PER_COMPANY = 60  # keeps one big employer from flooding the list


def load_companies(path: Path) -> list[dict]:
    return json.loads(path.read_text())["companies"]


def fetch_company(company: dict, fixtures: Path | None) -> tuple[dict, list[dict], str]:
    """Returns (company, raw jobs, error message or '')."""
    try:
        if fixtures:
            f = fixtures / f"{company['ats']}_{company['token']}.json"
            if not f.exists():
                return company, [], "no fixture"
            data = json.loads(f.read_text())
            parser = getattr(sources, f"parse_{company['ats']}")
            jobs = parser(data, company["token"]) if company["ats"] == "smartrecruiters" else parser(data)
        else:
            jobs = sources.FETCHERS[company["ats"]](company["token"])
        return company, jobs, ""
    except sources.FeedError as e:
        return company, [], str(e)
    except Exception as e:  # a format change at one company must not stop the run
        return company, [], f"{type(e).__name__}: {e}"


def build(companies: list[dict], previous: list[dict], fixtures: Path | None = None,
          today: str | None = None) -> tuple[list[dict], dict]:
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seen_before = {r["id"]: r for r in previous}
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda c: fetch_company(c, fixtures), companies))

    roles, per_company, failures = [], {}, {}
    for company, jobs, err in results:
        if err:
            failures[company["name"]] = err
            continue
        kept = [r for r in (to_role(j, company) for j in jobs) if r]
        # one card per company+title+city (multi-location duplicates)
        uniq = {}
        for r in kept:
            uniq.setdefault((r["title"].lower(), r["city"]), r)
        kept = sorted(uniq.values(), key=lambda r: r["posted"] or "0", reverse=True)[:MAX_PER_COMPANY]
        per_company[company["name"]] = {"total": len(jobs), "kept": len(kept)}
        roles += kept

    # first_seen: when Lamar first saw the role. Feeds without a date fall back to it.
    for r in roles:
        old = seen_before.get(r["id"])
        r["first_seen"] = old.get("first_seen", today) if old else today
        if not r["posted"]:
            r["posted"] = r["first_seen"]

    # A company that failed this run keeps its previous roles rather than vanishing.
    failed = set(failures)
    carried = [r for r in previous if r["company"] in failed]
    roles += carried

    roles.sort(key=lambda r: (r["first_seen"], r["posted"]), reverse=True)
    current = {r["id"] for r in roles}
    meta = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roles": len(roles),
        "new_today": sum(1 for r in roles if r["first_seen"] == today and r["id"] not in seen_before),
        "closed_since_last_run": sum(1 for rid, r in seen_before.items()
                                     if rid not in current and r["company"] not in failed),
        "by_country": {c: sum(1 for r in roles if r["country"] == c) for c in ("MY", "SG", "Remote")},
        "companies": per_company,
        "failures": failures,
        "carried_over_from_failed": len(carried),
    }
    return roles, meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--companies", type=Path, default=ROOT / "companies.json")
    ap.add_argument("--out", type=Path, default=ROOT / "data")
    ap.add_argument("--fixtures", type=Path, help="read saved feeds instead of the network")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    roles_path = args.out / "roles.json"
    previous = json.loads(roles_path.read_text()) if roles_path.exists() else []

    roles, meta = build(load_companies(args.companies), previous, args.fixtures)

    roles_path.write_text(json.dumps(roles, ensure_ascii=False, indent=0) + "\n")
    (args.out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    print(f"{meta['roles']} roles ({meta['new_today']} new, {meta['closed_since_last_run']} closed) "
          f"· MY {meta['by_country']['MY']} · SG {meta['by_country']['SG']} · Remote {meta['by_country']['Remote']}")
    for name, err in meta["failures"].items():
        print(f"  ! {name}: {err}", file=sys.stderr)
    ok = len(meta["companies"])
    if ok == 0:
        print("Every feed failed; keeping the previous data.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
