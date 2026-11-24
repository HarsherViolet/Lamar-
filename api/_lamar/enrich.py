"""Turn a RawJob into a Lamar role: market, city, level, function, skills."""
from __future__ import annotations

import hashlib
import re

# Place names that put a job in each market. Order matters: first match wins.
MY_PLACES = ["kuala lumpur", "petaling jaya", "selangor", "cyberjaya", "putrajaya", "subang",
             "shah alam", "bangsar", "penang", "george town", "johor", "malacca", "melaka",
             "ipoh", "kuching", "kota kinabalu", "malaysia", "kl,", " kl "]
SG_PLACES = ["singapore", "serangoon", " sg ", "sg -", "sg-", ", sg"]
REMOTE_APAC = ["apac", "apj", "asia", "southeast asia", "sea", "gmt+8", "utc+8"]

CITY_NAMES = {"kuala lumpur": "Kuala Lumpur", "petaling jaya": "Petaling Jaya", "cyberjaya": "Cyberjaya",
              "subang": "Subang Jaya", "shah alam": "Shah Alam", "penang": "Penang",
              "george town": "Penang", "johor": "Johor Bahru", "bangsar": "Kuala Lumpur",
              "singapore": "Singapore", "serangoon": "Singapore"}

SKILLS = ["sql", "python", "r", "excel", "tableau", "power bi", "looker", "dbt", "spark", "airflow",
          "bigquery", "snowflake", "databricks", "aws", "gcp", "azure", "kafka", "machine learning",
          "deep learning", "llm", "nlp", "statistics", "a/b testing", "experimentation", "forecasting",
          "credit risk", "fraud", "etl", "data modelling", "pytorch", "tensorflow", "javascript",
          "typescript", "react", "java", "go", "kubernetes", "mandarin", "bahasa"]

CONTACTS = {"Data": "Head of Data", "Engineering": "Engineering Manager", "Product": "Head of Product",
            "Design": "Head of Design", "Sales": "Head of Sales", "Marketing": "Head of Marketing",
            "Business": "Head of Strategy", "Operations": "Head of Operations"}


def market(locations: list[str], workplace: str, title: str) -> tuple[str, str] | None:
    """Return (country, city) for MY or SG jobs, ('Remote', ...) for APAC remote, else None."""
    for loc in locations:
        low = f" {loc.lower()} "
        if any(p in low for p in MY_PLACES):
            return "MY", next((v for k, v in CITY_NAMES.items() if k in low), "Kuala Lumpur")
        if any(p in low for p in SG_PLACES):
            return "SG", "Singapore"
    text = " ".join(locations + [title]).lower()
    if (workplace.lower() == "remote" or "remote" in text) and any(
            re.search(rf"\b{re.escape(p)}\b", text) for p in REMOTE_APAC):
        return "Remote", "Remote (APAC)"
    return None


def level(title: str) -> str:
    t = title.lower()
    if re.search(r"\bintern(ship)?\b|\btrainee\b|\bplacement\b", t):
        return "Intern"
    if re.search(r"\b(head|director|principal|staff|lead|vp|chief)\b", t) or "senior manager" in t:
        return "Lead"
    if re.search(r"\b(senior|sr\.?)\b", t):
        return "Senior"
    if re.search(r"\b(graduate|junior|jr\.?|fresh|entry|associate|executive|trainee|i)\b", t) \
            and not re.search(r"\bii+\b", t):
        return "Entry"
    return "Mid"


FUNCTION_RULES = [
    ("Product", r"product manager|product owner|\bpm\b"),
    ("Data", r"\bdata\b|analytic|scientist|machine learning|\bml\b|\bai\b|\bbi\b"),
    ("Business", r"strategy|business analyst|fp&a|consult"),
    ("Data", r"analyst|insight"),
    ("Design", r"design|\bux\b|\bui\b|user research"),
    ("Engineering", r"engineer|developer|devops|\bsre\b|architect|software|\bqa\b|security"),
    ("Sales", r"sales|account (executive|manager)|business development|\bbd\b|partnership"),
    ("Marketing", r"marketing|growth|brand|content|seo|community"),
    ("Business", r"finance|controller|treasury|risk|legal|counsel|compliance"),
]


def _match(text: str) -> str | None:
    t = text.lower()
    for name, pat in FUNCTION_RULES:
        if re.search(pat, t):
            return name
    return None


def function(title: str, department: str) -> str:
    """Label by what the job is, not by its qualifiers.

    The part of a title before any bracket, comma or dash says what the job is
    ("Product Design Intern"); what follows qualifies it ("(Design Systems & AI
    Workflows)", ", Data Platform"). Read the head first, then the full title,
    then the department.
    """
    head = re.split(r"\s*[(\[,|]|\s[-–—]\s", title, maxsplit=1)[0]
    return _match(head) or _match(title) or _match(department) or "Operations"


def mode(workplace: str, locations: list[str], description: str) -> str:
    w = (workplace or "").lower()
    if "remote" in w:
        return "Remote"
    if "hybrid" in w:
        return "Hybrid"
    if "site" in w or "office" in w:
        return "On-site"
    blob = " ".join(locations).lower() + " " + description[:1500].lower()
    if "hybrid" in blob:
        return "Hybrid"
    if re.search(r"\bfully remote\b|\bremote\b", " ".join(locations).lower()):
        return "Remote"
    return "On-site"


def skills(text: str) -> list[str]:
    low = f" {text.lower()} "
    found = [s for s in SKILLS if re.search(rf"(?<![a-z]){re.escape(s)}(?![a-z])", low)]
    return found[:6]


SALARY_RE = re.compile(r"(RM|MYR|SGD|S\$)\s?[\d,]+(?:\.\d+)?\s?k?\s?(?:-|–|to)\s?(?:RM|MYR|SGD|S\$)?\s?[\d,]+(?:\.\d+)?\s?k?"
                       r"(?:\s?(?:per|/)\s?(?:month|mth|year|annum|yr))?", re.I)


def salary(given: str, description: str) -> str:
    if given:
        return given
    m = SALARY_RE.search(description or "")
    return m.group(0).strip() if m else ""


def summary(description: str) -> str:
    """First real sentence of the ad, trimmed for a card."""
    for line in (description or "").split("\n"):
        line = line.strip(" -•*\t")
        if len(line) < 40 or line.lower().startswith(("about", "who we are", "company")):
            continue
        sent = re.split(r"(?<=[.!?])\s", line)[0]
        return sent if len(sent) <= 180 else sent[:177].rsplit(" ", 1)[0] + "…"
    return ""


def role_id(company: str, source_id: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")[:20]
    h = hashlib.sha1(f"{company}|{source_id}|{title}".encode()).hexdigest()[:8]
    return f"{slug}-{h}"


# Frontline logistics and retail roles crowd out the office roles Lamar is for.
EXCLUDE = re.compile(r"\b(driver|rider|lorry|truck|delivery (staff|attendant)|fleet assistant|warehouse assistant"
                     r"|operator|sales assistant|retail assistant|cashier|cleaner|technician)\b", re.I)


def to_role(job: dict, company: dict) -> dict | None:
    where = market(job["locations"], job["workplace"], job["title"])
    if not where or not job["title"] or not job["url"] or EXCLUDE.search(job["title"]):
        return None
    country, city = where
    fn = function(job["title"], job["department"])
    desc = job["description"]
    return {
        "id": role_id(company["name"], job["source_id"], job["title"]),
        "company": company["name"],
        "about": company.get("about", ""),
        "title": job["title"].strip(),
        "city": city,
        "country": country,
        "mode": "Remote" if country == "Remote" else mode(job["workplace"], job["locations"], desc),
        "level": level(job["title"]),
        "fn": fn,
        "posted": job["posted"],
        "salary": salary(job["salary"], desc),
        "url": job["url"],
        "source": company["ats"].capitalize() if company["ats"] != "smartrecruiters" else "SmartRecruiters",
        "contact": CONTACTS.get(fn, "Hiring Manager"),
        "note": summary(desc) or job["department"],
        "tags": skills(f"{job['title']} {desc}"),
    }
