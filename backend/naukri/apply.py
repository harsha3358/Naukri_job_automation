import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from backend.naukri import selectors

log = logging.getLogger(__name__)

JOB_DATA_TIMEOUT_MS = 20_000
BUTTON_TIMEOUT_MS = 15_000
APPLY_ANSWER_TIMEOUT_MS = 25_000
SETTLE_MS = 1_500


class JobPageKind(StrEnum):
    DIRECT = "direct"  # Naukri's own Apply button
    COMPANY_SITE = "company_site"  # "Apply on company site"
    ALREADY_APPLIED = "already_applied"
    LOGGED_OUT = "logged_out"  # Naukri answered as if nobody is logged in
    UNKNOWN = "unknown"  # the page did not turn out as any of these


@dataclass
class JobPage:
    kind: JobPageKind
    company_url: str = ""
    applied_at: datetime | None = None  # naive UTC, for ALREADY_APPLIED


@dataclass
class ApplyResult:
    applied: bool
    message: str = ""
    # Naukri's own count of today's applications and its daily ceiling, when it reports them.
    daily_applied: int | None = None
    daily_quota: int | None = None


def open_job(page: Page, url: str) -> JobPage:
    """Open a job's page in the logged-in browser and see how it can be applied to. Clicks nothing.

    The buttons alone cannot be trusted: Naukri first paints a plain Apply button for every job
    and only swaps it for "Apply on company site" once the job's data has loaded (seen
    2026-10-04: a company-site job read as a normal one). So the page's own job data decides,
    and the button must then agree with it.
    """
    try:
        with page.expect_response(
            lambda response: selectors.JOB_DATA_PATH in response.url, timeout=JOB_DATA_TIMEOUT_MS
        ) as answer:
            page.goto(url, wait_until="domcontentloaded")
        response = answer.value
        job_data = response.json() if response.ok else {}
    except (PlaywrightTimeout, ValueError):  # no job data came, or it was not JSON
        return JobPage(JobPageKind.UNKNOWN)

    details = job_data.get("jobDetails")
    if not isinstance(details, dict):
        return JobPage(JobPageKind.UNKNOWN)
    if job_data.get("loggedIn") is not True:
        return JobPage(JobPageKind.LOGGED_OUT)
    if details.get("applyDate"):
        return JobPage(JobPageKind.ALREADY_APPLIED, applied_at=_naukri_time(details["applyDate"]))

    company_site = bool(details.get("applyRedirectUrl"))
    expected, other = selectors.COMPANY_SITE_BUTTON, selectors.APPLY_BUTTON
    if not company_site:
        expected, other = other, expected
    try:
        page.wait_for_selector(expected, state="visible", timeout=BUTTON_TIMEOUT_MS)
    except PlaywrightTimeout:
        return JobPage(JobPageKind.UNKNOWN)
    page.wait_for_timeout(SETTLE_MS)
    if page.query_selector(other) or not page.query_selector(expected):
        return JobPage(JobPageKind.UNKNOWN)  # data and buttons disagree, so do not guess

    if company_site:
        return JobPage(JobPageKind.COMPANY_SITE, company_url=_web_address(details["applyRedirectUrl"]))
    return JobPage(JobPageKind.DIRECT)


def click_apply(page: Page, naukri_job_id: str) -> ApplyResult:
    """Click Apply once, on a page `open_job` has just read as DIRECT, and report Naukri's answer.

    Counts as applied only when Naukri's own answer says so for this job. Anything else, such as
    a recruiter's questions, comes back as not applied; nothing further is clicked or typed.
    """
    try:
        with page.expect_response(
            lambda response: selectors.APPLY_REQUEST_PATH in response.url, timeout=APPLY_ANSWER_TIMEOUT_MS
        ) as answer:
            page.click(selectors.APPLY_BUTTON)
        response = answer.value
        body = response.json() if response.ok else {}
    except (PlaywrightTimeout, ValueError):
        return ApplyResult(applied=False, message="Naukri gave no answer to the Apply click.")
    if not isinstance(body, dict):
        return ApplyResult(applied=False, message="Naukri's answer to the Apply click could not be read.")

    status = (body.get("applyStatus") or {}).get(str(naukri_job_id))
    entry = next((job for job in body.get("jobs") or [] if str(job.get("jobId")) == str(naukri_job_id)), {})
    quota = body.get("quotaDetails") or {}
    return ApplyResult(
        applied=status == selectors.APPLIED_STATUS and entry.get("status") == selectors.APPLIED_STATUS,
        message=str(entry.get("message") or "")[:300],
        daily_applied=quota.get("dailyApplied") if isinstance(quota.get("dailyApplied"), int) else None,
        daily_quota=quota.get("dailyQuota") if isinstance(quota.get("dailyQuota"), int) else None,
    )


def _web_address(url: object) -> str:
    # Shown to the user as a clickable link, so only a plain web address is accepted.
    return url if isinstance(url, str) and url.startswith(("https://", "http://")) else ""


def _naukri_time(value: object) -> datetime | None:
    """Naukri's "2026-10-04 08:36:13" is in the PC's local time (it matched the clock when seen)."""
    try:
        local = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").astimezone()
    except ValueError:
        return None
    return local.astimezone(timezone.utc).replace(tzinfo=None)
