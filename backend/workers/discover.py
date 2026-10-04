import logging

from playwright.sync_api import Error as PlaywrightError
from sqlalchemy import select

from backend.core.clock import utcnow
from backend.db.database import SessionLocal
from backend.db.models import CandidateProfile, Run, SearchProfile
from backend.naukri.browser import BrowserUnavailable, open_browser
from backend.naukri.discovery import NaukriPageError, search_role
from backend.services.ingest import ingest_jobs

log = logging.getLogger(__name__)

RUN_KIND = "discover"


def run_discovery() -> None:
    """Search Naukri for every switched-on role and feed what is found into the matcher.

    Always leaves a finished `runs` row behind, with the reason if it could not complete.
    Any page the tool does not understand stops the whole run: better no jobs than wrong ones.
    """
    with SessionLocal() as db:
        run = Run(kind=RUN_KIND)
        db.add(run)
        db.commit()
        error = ""
        try:
            roles = db.scalars(select(SearchProfile).where(SearchProfile.is_active).order_by(SearchProfile.id)).all()
            if not roles:
                raise NaukriPageError("No role is switched on. Add or switch on a role on the Roles page.")
            experience = db.get(CandidateProfile, 1).experience_years
            with open_browser() as context:
                page = context.pages[0] if context.pages else context.new_page()
                for role in roles:
                    search = search_role(page, role, experience)
                    result = ingest_jobs(db, search.jobs, role)
                    run.found += len(search.jobs)
                    run.matched += result.queued + result.manual
                    run.skipped += result.skipped
                    # For a search run, "failed" counts the pages Naukri answered with "No result found".
                    run.failed += search.no_result_pages
                    db.commit()
        except (NaukriPageError, BrowserUnavailable) as exc:
            error = str(exc)
        except PlaywrightError as exc:
            log.warning("Search stopped by a browser error: %s", exc)
            error = "The browser window was closed or stopped responding before the search finished."
        except Exception:  # whatever happens, the run must end with a reason the user can read
            log.exception("Search crashed")
            error = "Something unexpected went wrong. The details are in the log file."
        finally:
            db.rollback()  # drop anything half-done from a failed step, then record how the run ended
            run.error = error
            run.finished_at = utcnow()
            db.commit()
            log.info("Search finished: found=%d matched=%d skipped=%d error=%r", run.found, run.matched, run.skipped, error)
