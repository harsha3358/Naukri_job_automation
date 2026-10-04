"""Turns the text on a Naukri job card into numbers and dates. No browser needed, so fully testable."""

import re
from datetime import date, timedelta
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from backend.naukri.selectors import BASE_URL
from backend.services.ingest import JobData

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(cr|lac|lakh)?")
_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_EXPERIENCE_IN_URL = re.compile(r"-(\d+)-to-(\d+)-years-")
_RUPEES_PER_LAKH = 100_000


def build_search_url(role: str, city: str | None, experience_years: float | None, max_job_age_days: int) -> str:
    """The same address Naukri's own search box produces for this role, city and filters."""
    keyword = " ".join(role.lower().split())
    slug = _NOT_SLUG.sub("-", keyword).strip("-") + "-jobs"
    params: dict[str, str | int] = {"k": keyword}
    if city:
        place = " ".join(city.lower().split())
        slug += "-in-" + _NOT_SLUG.sub("-", place).strip("-")
        params["l"] = place
    if experience_years is not None:
        params["experience"] = int(experience_years)
    params["jobAge"] = max_job_age_days
    return f"{BASE_URL}/{slug}?{urlencode(params, quote_via=quote)}"


def next_page_url(current_url: str, current_page: int) -> str:
    """Address of the results page after `current_page`, built from the address the browser is on.

    Naukri rewrites the city in the address ("-in-hyderabad" becomes "-in-hyderabad-secunderabad"),
    and the page number goes after that rewritten name, so it has to start from the real address.
    """
    parts = urlsplit(current_url)
    path = parts.path
    suffix = f"-{current_page}"
    if current_page > 1 and path.endswith(suffix):
        path = path[: -len(suffix)]
    return urlunsplit(parts._replace(path=f"{path}-{current_page + 1}"))


def parse_experience(text: str, url: str = "") -> tuple[int | None, int | None]:
    """"0-1 Yrs" -> (0, 1). Internship cards show no experience, so fall back to the job link."""
    numbers = [int(float(number)) for number in _NUMBER.findall(text)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    if len(numbers) == 1:
        return (numbers[0], None) if "+" in text else (numbers[0], numbers[0])
    in_url = _EXPERIENCE_IN_URL.search(url)
    return (int(in_url.group(1)), int(in_url.group(2))) if in_url else (None, None)


def parse_salary(text: str) -> tuple[float | None, float | None]:
    """Salary range in lakhs per year. (None, None) when the card does not disclose it."""
    lowered = text.lower().replace(",", "")
    if "unpaid" in lowered:
        return 0.0, 0.0
    amounts = _AMOUNT.findall(lowered)
    if not amounts:
        return None, None

    # "2-5 Lacs": the first number has no unit of its own, so it takes the next one's.
    values: list[float] = []
    unit_after = ""
    for number, unit in reversed(amounts):
        unit_after = unit or unit_after
        if unit_after == "cr":
            lakhs = float(number) * 100
        elif unit_after:
            lakhs = float(number)
        else:
            lakhs = float(number) / _RUPEES_PER_LAKH
        values.append(lakhs * 12 if "month" in lowered else lakhs)
    values.reverse()
    return round(values[0], 2), round(values[-1], 2)


def parse_posted(text: str, today: date) -> date | None:
    """"4 days ago" -> a date. None for anything that is not an age, like "Starts in 1-3 months"."""
    lowered = text.lower()
    if any(word in lowered for word in ("just now", "today", "hour", "minute")):
        return today
    number = _NUMBER.search(lowered)
    if "ago" not in lowered or not number:
        return None
    count = int(float(number.group()))
    if "day" in lowered:
        return today - timedelta(days=count)
    if "week" in lowered:
        return today - timedelta(weeks=count)
    if "month" in lowered:
        return today - timedelta(days=30 * count)
    return None


def job_from_card(card: dict, today: date) -> JobData | None:
    """One job card, as read from the page, to a job. None if the card has no ID or title."""
    job_id = (card.get("id") or "").strip()
    title = (card.get("title") or "").strip()
    if not job_id or not title:
        return None
    url = card.get("url") or ""
    experience_min, experience_max = parse_experience(card.get("experience") or "", url)
    salary_min, salary_max = parse_salary(card.get("salary") or "")
    return JobData(
        naukri_job_id=job_id,
        title=title[:300],
        company=(card.get("company") or "").strip()[:300],
        location=(card.get("location") or "").strip()[:300],
        experience_min=experience_min,
        experience_max=experience_max,
        salary_min_lpa=salary_min,
        salary_max_lpa=salary_max,
        skills=[skill.strip() for skill in card.get("skills") or [] if skill.strip()],
        description=(card.get("description") or "").strip(),
        url=url[:600],
        posted_on=parse_posted(card.get("posted") or "", today),
    )
