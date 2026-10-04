import logging
import random
from dataclasses import dataclass, field
from datetime import date

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from backend.db.models import SearchProfile
from backend.naukri import selectors
from backend.naukri.evidence import save_evidence
from backend.naukri.parse import build_search_url, job_from_card, next_page_url
from backend.services.ingest import JobData

log = logging.getLogger(__name__)

# Kept small on purpose: every page load is automated traffic on the user's account.
# One page for now: on the owner's first real search (2026-10-04) the address used for page 2
# came back with page 1 again. The address is now built from the one Naukri redirects to, but
# that has not been checked against the live site, so do not raise this until it has been.
MAX_PAGES_PER_SEARCH = 1
PAUSE_SECONDS = (4.0, 9.0)
RESULTS_TIMEOUT_MS = 25_000


class NaukriPageError(Exception):
    """Naukri showed something the tool does not understand. The run stops instead of guessing."""


@dataclass
class RoleSearch:
    jobs: list[JobData] = field(default_factory=list)
    # Result pages on which Naukri said "No result found". It says this for a search that truly
    # has no jobs, and also, as seen on 2026-10-04, to a browser it suspects of being automated
    # (while a normal browser gets real results for the same search). The two look identical.
    no_result_pages: int = 0


def search_role(page: Page, role: SearchProfile, experience_years: float | None) -> RoleSearch:
    """Jobs for one role: one search per city on the role, a few result pages each."""
    result = RoleSearch()
    for city in role.locations or [None]:
        url = build_search_url(role.role, city, experience_years, role.max_job_age_days)
        seen_ids: set[str] = set()
        for page_number in range(1, MAX_PAGES_PER_SEARCH + 1):
            cards = _read_results(page, url)
            _pause(page)
            if cards is None:
                log.info("Search %r in %s, page %d: Naukri said no result", role.role, city or "any city", page_number)
                result.no_result_pages += 1
                break
            fresh = [card for card in cards if card.get("id") not in seen_ids]
            if not fresh:
                # Naukri served a page already read (a wrong page address sends it back to page 1).
                log.warning("Search %r in %s: page %d repeated an earlier page", role.role, city or "any city", page_number)
                break
            seen_ids.update(card.get("id") for card in fresh)
            found = [job for job in (job_from_card(card, date.today()) for card in fresh) if job]
            log.info("Search %r in %s, page %d: %d jobs", role.role, city or "any city", page_number, len(found))
            result.jobs.extend(found)
            if len(cards) < selectors.RESULTS_PER_PAGE:
                break
            url = next_page_url(page.url, page_number)
    return result


def _read_results(page: Page, url: str) -> list[dict] | None:
    """The job cards on one results page, or None when Naukri says it has no result.

    A "no result" page can still show job cards: suggestions that do not match the search.
    Those are never returned.
    """
    page.goto(url, wait_until="domcontentloaded")
    try:
        # "attached": present in the page. The default also demands the first match be visible,
        # which stalls when that first match is one of Naukri's hidden placeholders.
        page.wait_for_selector(
            f"{selectors.JOB_CARD}, {selectors.NO_RESULTS}, {selectors.FALLBACK_NOTICE}",
            state="attached",
            timeout=RESULTS_TIMEOUT_MS,
        )
    except PlaywrightTimeout:
        evidence = save_evidence(page, "search")
        raise NaukriPageError(
            "Naukri did not show a list of jobs. It may be asking for a check, or its page may have changed. "
            f"A picture of what it showed was saved to {evidence}."
        ) from None
    if page.query_selector(f"{selectors.NO_RESULTS}, {selectors.FALLBACK_NOTICE}"):
        return None
    return page.eval_on_selector_all(
        selectors.JOB_CARD,
        selectors.READ_CARDS_JS,
        {"link": selectors.CARD_LINK, "skill": selectors.CARD_SKILL, "fields": selectors.CARD_TEXT_FIELDS},
    )


def _pause(page: Page) -> None:
    page.wait_for_timeout(random.uniform(*PAUSE_SECONDS) * 1000)
