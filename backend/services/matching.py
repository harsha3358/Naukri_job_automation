"""Decides whether a job fits one of the user's roles, and how well (0-100).

Two stages:

1. Filters. Things the user stated as limits (cities, lowest salary, job age, excluded words
   and companies) and a clear experience gap. Failing any one rejects the job outright,
   because every wasted application costs part of the daily limit.
2. Score. Title, skills and experience fit, weighted. A part with nothing to compare (the job
   lists no skills, say) is left out and the rest re-scaled, so missing data neither helps
   nor hurts.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from backend.db.models import CandidateProfile, Job, SearchProfile
from backend.services.skills import SKILLS, canonical_skill, find_skills

WEIGHTS = {"title": 45, "skills": 40, "experience": 15}
# Jobs list many tags; matching this share of them already counts as a full skills match.
FULL_SKILL_OVERLAP = 0.7
# A job may ask for this many more years than the user has before it is rejected.
EXPERIENCE_GAP_ALLOWED = 1

_COMPOUNDS = [
    (re.compile(r"\bfront[\s-]end\b"), "frontend"),
    (re.compile(r"\bback[\s-]end\b"), "backend"),
    (re.compile(r"\bfull[\s-]stack\b"), "fullstack"),
]
_TOKEN = re.compile(r"[a-z0-9+#]+(?:\.[a-z0-9]+)*")
_TOKEN_ALIASES = {"engineer": "developer", "programmer": "developer", "dev": "developer", "sr": "senior", "jr": "junior"}
_PLACE_ALIASES = {
    "bengaluru": "bangalore",
    "gurugram": "gurgaon",
    "new delhi": "delhi",
    "bombay": "mumbai",
    "madras": "chennai",
    "calcutta": "kolkata",
    "trivandrum": "thiruvananthapuram",
    "cochin": "kochi",
    "vizag": "visakhapatnam",
    "work from home": "remote",
    "wfh": "remote",
}

# (passed, note). The note explains a failure, or records what was checked.
Check = tuple[bool, str | None]
# (0..1 or None when there is nothing to compare, note)
Component = tuple[float | None, str | None]


@dataclass
class MatchResult:
    score: int
    notes: list[str] = field(default_factory=list)
    excluded: bool = False


def score_job(job: Job, role: SearchProfile, candidate: CandidateProfile, today: date | None = None) -> MatchResult:
    checks = [
        _check_excluded_words(job, role),
        _check_excluded_companies(job, role),
        _check_location(job, role),
        _check_salary(job, role),
        _check_freshness(job, role, today or date.today()),
        _check_experience(job, candidate),
    ]
    failures = [note for passed, note in checks if not passed]
    if failures:
        return MatchResult(score=0, notes=failures, excluded=True)

    parts: dict[str, Component] = {
        "title": _title(job, role),
        "skills": _skills(job, candidate),
        "experience": _experience(job, candidate),
    }
    known = {name: value for name, (value, _) in parts.items() if value is not None}
    total_weight = sum(WEIGHTS[name] for name in known)
    earned = sum(WEIGHTS[name] * value for name, value in known.items())
    notes = [note for _, note in parts.values() if note] + [note for _, note in checks if note]
    return MatchResult(score=round(100 * earned / total_weight), notes=notes)


# --- filters -----------------------------------------------------------------


def _check_excluded_words(job: Job, role: SearchProfile) -> Check:
    title = job.title.lower()
    for word in role.exclude_keywords or []:
        if re.search(rf"(?<![a-z0-9]){re.escape(word.lower())}(?![a-z0-9])", title):
            return False, f'Title contains "{word}", which you chose to skip'
    return True, None


def _check_excluded_companies(job: Job, role: SearchProfile) -> Check:
    company = (job.company or "").lower()
    for name in role.exclude_companies or []:
        if name.lower() in company:
            return False, f"{job.company} is on your list of companies to skip"
    return True, None


def _normalize_place(text: str) -> str:
    text = text.lower()
    for alias, name in _PLACE_ALIASES.items():
        text = re.sub(rf"\b{re.escape(alias)}\b", name, text)
    return text


def _check_location(job: Job, role: SearchProfile) -> Check:
    wanted = role.locations or []
    if not wanted or not job.location:
        return True, None
    place = _normalize_place(job.location)
    for city in wanted:
        if _normalize_place(city) in place:
            return True, f"Location: {city} is one of your cities"
    return False, f"Location: {job.location} is not one of your cities"


def _check_salary(job: Job, role: SearchProfile) -> Check:
    minimum = role.min_salary_lpa
    if minimum is None:
        return True, None
    offered = job.salary_max_lpa if job.salary_max_lpa is not None else job.salary_min_lpa
    if offered is None:
        return True, "Salary: not disclosed"
    if offered < minimum:
        return False, f"Salary: up to {offered:g} LPA is below your lowest of {minimum:g} LPA"
    return True, f"Salary: up to {offered:g} LPA meets your lowest"


def _check_freshness(job: Job, role: SearchProfile, today: date) -> Check:
    if job.posted_on is None:
        return True, None
    age = (today - job.posted_on).days
    if age > role.max_job_age_days:
        return False, f"Posted {age} days ago, older than your {role.max_job_age_days}-day limit"
    return True, f"Posted {age} day{'' if age == 1 else 's'} ago"


def _check_experience(job: Job, candidate: CandidateProfile) -> Check:
    have, low = candidate.experience_years, job.experience_min
    if have is None or low is None or low - have <= EXPERIENCE_GAP_ALLOWED:
        return True, None
    return False, f"Experience: job needs {low}+ yrs, you have {have:g}"


# --- score -------------------------------------------------------------------


def _title_tokens(text: str) -> list[str]:
    text = text.lower()
    for pattern, replacement in _COMPOUNDS:
        text = pattern.sub(replacement, text)
    tokens: list[str] = []
    for token in _TOKEN.findall(text):
        # "react.js" / "reactjs" -> "react", but leave a bare "js" alone
        if token.endswith(".js"):
            token = token[:-3]
        elif token.endswith("js") and len(token) > 4:
            token = token[:-2]
        token = _TOKEN_ALIASES.get(token, token)
        if token not in tokens:
            tokens.append(token)
    return tokens


def _title(job: Job, role: SearchProfile) -> Component:
    wanted = _title_tokens(role.role)
    if not wanted:
        return 0.0, "Title: role is empty"
    title = _title_tokens(job.title)
    matched = sum(1 for token in wanted if token in title)
    # Squared so a half match ("Backend Developer" for "Frontend Developer") earns little.
    return (matched / len(wanted)) ** 2, f"Title: {matched} of {len(wanted)} role words found"


def _skills(job: Job, candidate: CandidateProfile) -> Component:
    have = {canonical_skill(skill).lower() for skill in candidate.skills or []}
    if not have:
        return None, "Skills: add skills to your profile to compare"

    # Naukri pads a job's tags with filler ("Computer science", "Coding", "Development").
    # Only tags that are real skills count: ones in the vocabulary, or ones the user lists.
    wanted: list[str] = []
    for tag in job.skills or []:
        name = canonical_skill(tag)
        if name not in wanted and (name in SKILLS or name.lower() in have):
            wanted.append(name)
    if not wanted:
        wanted = find_skills(job.description or "")
    if not wanted:
        return None, "Skills: the job names none the tool recognises"

    matched = [skill for skill in wanted if skill.lower() in have]
    note = f"Skills: {len(matched)} of {len(wanted)} match"
    if matched:
        note += f" ({', '.join(matched[:6])})"
    return min(1.0, len(matched) / len(wanted) / FULL_SKILL_OVERLAP), note


def _experience(job: Job, candidate: CandidateProfile) -> Component:
    have = candidate.experience_years
    low, high = job.experience_min, job.experience_max
    if have is None:
        return None, "Experience: not set in your profile"
    if low is None and high is None:
        return None, "Experience: not stated on the job"

    if low is not None and high is not None:
        wanted = f"{low}-{high} yrs"
    elif low is not None:
        wanted = f"{low}+ yrs"
    else:
        wanted = f"up to {high} yrs"

    if low is not None and have < low:
        return 0.5, f"Experience: job wants {wanted}, you have {have:g}"
    if high is not None and have > high:
        return 0.5, f"Experience: you are above the {wanted} range"
    return 1.0, f"Experience: fits {wanted}"
