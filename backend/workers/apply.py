import logging
import random

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.core.clock import start_of_local_day_utc, to_local, utcnow
from backend.db.database import SessionLocal
from backend.db.models import (
    CV,
    Application,
    ApplicationState,
    ApplyMode,
    AppSettings,
    ApplyType,
    Job,
    Run,
    SearchProfile,
)
from backend.naukri.apply import JobPageKind, click_apply, open_job
from backend.naukri.browser import BrowserUnavailable, open_browser
from backend.naukri.evidence import save_evidence
from backend.naukri.session import is_logged_in
from backend.services.sheets_sync import SHEET_STATES, queue_for_sheet, sync_pending

log = logging.getLogger(__name__)

RUN_KIND = "apply"
# Seconds between jobs. Opening and reading a page is quick; real applications are spaced out,
# because applying in bursts is what gets accounts restricted.
PAUSE_AFTER_LOOK = (4.0, 9.0)
PAUSE_AFTER_APPLY = (30.0, 90.0)
# This many jobs in a row that could not be read or applied to stops the run: Naukri's page has
# probably changed or it is refusing the tool, and carrying on would only make it worse.
MAX_PROBLEMS_IN_A_ROW = 3


class ApplyStopped(Exception):
    """The run cannot go on. The message is safe to show to the user."""


def run_apply() -> None:
    """Work through the jobs that are waiting, best match first, within today's limit.

    In practice mode every job page is opened and read, but Apply is never clicked.
    Always leaves a finished `runs` row behind, with the reason if it could not complete.
    """
    with SessionLocal() as db:
        app_settings = db.get(AppSettings, 1)
        practice = app_settings.apply_mode != ApplyMode.REAL
        run = Run(kind=RUN_KIND)
        db.add(run)
        db.commit()
        error = ""
        try:
            jobs = _waiting_jobs(db, _left_today(db, app_settings))
            if not jobs:
                raise ApplyStopped("No job is waiting to be applied to, or today's limit is used up.")
            with open_browser() as context:
                page = context.pages[0] if context.pages else context.new_page()
                if not is_logged_in(page):
                    _mark_logged_out(db)
                    raise ApplyStopped("Naukri is not logged in. Click Connect Naukri on the Settings page and log in.")
                _work_through(db, page, jobs, run, practice)
        except (ApplyStopped, BrowserUnavailable) as exc:
            error = str(exc)
        except PlaywrightError as exc:
            log.warning("Apply run stopped by a browser error: %s", exc)
            error = "The browser window was closed or stopped responding before the run finished."
        except Exception:  # whatever happens, the run must end with a reason the user can read
            log.exception("Apply run crashed")
            error = "Something unexpected went wrong. The details are in the log file."
        finally:
            db.rollback()  # drop anything half-done from a failed step, then record how the run ended
            run.error = error
            run.finished_at = utcnow()
            db.commit()
            log.info(
                "Apply run finished (practice=%s): looked_at=%d applied=%d would_apply=%d company_site=%d problems=%d error=%r",
                practice, run.found, run.applied, run.matched, run.skipped, run.failed, error,
            )
            sync_pending(db)  # copy what changed to the user's Sheet; anything unsent stays queued


def _left_today(db: Session, app_settings: AppSettings) -> int:
    applied_today = db.scalar(
        select(func.count()).select_from(Application).where(Application.applied_at >= start_of_local_day_utc())
    )
    return max(0, app_settings.daily_apply_cap - applied_today)


def _waiting_jobs(db: Session, limit: int) -> list[Job]:
    """Real jobs that are waiting, whose role is still switched on, best match first."""
    if limit <= 0:
        return []
    return list(
        db.scalars(
            select(Job)
            .join(Application)
            .join(SearchProfile, Job.search_profile_id == SearchProfile.id)
            .where(
                Application.state == ApplicationState.QUEUED,
                ~Job.is_demo,
                Job.url != "",
                SearchProfile.is_active,
            )
            .options(joinedload(Job.application))
            .order_by(Job.match_score.desc(), Job.id)
            .limit(limit)
        )
    )


def _mark_logged_out(db: Session) -> None:
    db.get(AppSettings, 1).naukri_connected_at = None
    db.commit()


def _work_through(db: Session, page: Page, jobs: list[Job], run: Run, practice: bool) -> None:
    """For an apply run the counters mean: found = job pages opened, applied = applications sent,
    matched = would apply (practice), skipped = company-site jobs set aside, failed = problems."""
    active_cv_id = db.scalar(select(CV.id).where(CV.is_active))
    problems_in_a_row = 0
    for job in jobs:
        application = job.application
        job_page = open_job(page, job.url)
        if job_page.kind == JobPageKind.LOGGED_OUT:
            _mark_logged_out(db)
            raise ApplyStopped("Naukri logged the tool out. Click Connect Naukri on the Settings page and log in again.")
        run.found += 1
        stamp = f"{to_local(utcnow()):%d %b, %H:%M}"
        pause = PAUSE_AFTER_LOOK
        problem = False
        naukri_limit_reached = False

        if job_page.kind == JobPageKind.COMPANY_SITE:
            job.apply_type = ApplyType.EXTERNAL
            job.company_apply_url = job_page.company_url
            application.state = ApplicationState.EXTERNAL
            application.notes = f"{stamp}: this job is applied to on the company's own site. Use the link."
            run.skipped += 1
        elif job_page.kind == JobPageKind.ALREADY_APPLIED:
            application.state = ApplicationState.APPLIED
            application.applied_at = job_page.applied_at or utcnow()
            application.notes = f"{stamp}: Naukri shows you had already applied to this job."
        elif job_page.kind == JobPageKind.UNKNOWN:
            evidence = save_evidence(page, "job")
            application.notes = f"{stamp}: no Apply button was found on the job's page. A picture was saved: {evidence}"
            problem = True
        elif practice:
            job.apply_type = ApplyType.DIRECT
            application.notes = f"{stamp}: practice run. The Apply button is there. It was not clicked."
            run.matched += 1
        else:
            job.apply_type = ApplyType.DIRECT
            application.attempts += 1
            result = click_apply(page, job.naukri_job_id)
            pause = PAUSE_AFTER_APPLY
            if result.applied:
                application.state = ApplicationState.APPLIED
                application.applied_at = utcnow()
                application.cv_id = active_cv_id
                application.notes = f"{stamp}: applied. Naukri said: {result.message or 'application received'}"
                run.applied += 1
                naukri_limit_reached = (
                    result.daily_applied is not None
                    and result.daily_quota is not None
                    and result.daily_applied >= result.daily_quota
                )
            else:
                # Never retried by itself: the click may have gone through even without a clear answer.
                evidence = save_evidence(page, "apply")
                application.state = ApplicationState.NEEDS_MANUAL
                application.last_error = result.message
                application.notes = (
                    f"{stamp}: Naukri did not confirm the application"
                    f"{': ' + result.message if result.message else ''}. It may be asking questions. "
                    f"Open the job and check it yourself. A picture was saved: {evidence}"
                )
                problem = True

        if problem:
            run.failed += 1
            problems_in_a_row += 1
        else:
            problems_in_a_row = 0
        if application.state in SHEET_STATES:
            queue_for_sheet(db, application)
        db.commit()

        if problems_in_a_row >= MAX_PROBLEMS_IN_A_ROW:
            raise ApplyStopped(
                f"{MAX_PROBLEMS_IN_A_ROW} jobs in a row could not be read or applied to, so the run stopped. "
                "Naukri's page may have changed, or it may be asking for a check. Pictures were saved in the screenshots folder."
            )
        if naukri_limit_reached:
            raise ApplyStopped("Naukri's own limit of applications for today is reached, so the run stopped.")
        if job is not jobs[-1]:
            page.wait_for_timeout(random.uniform(*pause) * 1000)
