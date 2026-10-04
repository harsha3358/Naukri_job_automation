"""Copies applications to the user's own Google Sheet.

The database is the truth and the Sheet is a copy. Every application that should be on the
Sheet gets a row in `sheet_outbox`; rows stay there until Google has confirmed them, so a
missing connection or a network failure loses nothing. The Sheet side is a small script the
user adds to their Sheet (sheets/applications_sheet.gs); it keeps one row per Naukri job ID.
"""

import logging
import re
import threading
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.core.clock import to_local, utcnow
from backend.core.webhook import is_apps_script_link, post_json
from backend.db.database import SessionLocal
from backend.db.models import CV, Application, ApplicationState, AppSettings, Job, SearchProfile, SheetOutbox

log = logging.getLogger(__name__)

_SHEET_URL = re.compile(r"^https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]{20,})")

# What goes on the Sheet: applications sent, and jobs the user has to act on.
SHEET_STATES = (
    ApplicationState.APPLIED,
    ApplicationState.EXTERNAL,
    ApplicationState.NEEDS_MANUAL,
    ApplicationState.FAILED,
)
STATUS_ON_SHEET = {
    ApplicationState.APPLIED: "Applied",
    ApplicationState.EXTERNAL: "Apply on company site",
    ApplicationState.NEEDS_MANUAL: "Apply by hand",
    ApplicationState.FAILED: "Failed",
}
ROWS_PER_REQUEST = 50


@dataclass
class SyncResult:
    sent: int = 0
    error: str = ""  # safe to show to the user


def sheet_id_from_url(url: str) -> str | None:
    """The spreadsheet ID inside a Google Sheets link, or None if it is not one."""
    match = _SHEET_URL.match(url.strip())
    return match.group(1) if match else None


def queue_for_sheet(db: Session, application: Application) -> None:
    """Mark an application as needing to be written to the Sheet. The caller commits."""
    waiting = db.scalar(
        select(SheetOutbox.id).where(SheetOutbox.application_id == application.id, SheetOutbox.synced_at.is_(None)).limit(1)
    )
    if waiting is None:
        db.add(SheetOutbox(application_id=application.id))


def queue_everything(db: Session) -> int:
    """Queue every application that belongs on the Sheet, e.g. after the Sheet is first connected."""
    applications = db.scalars(
        select(Application).join(Job).where(Application.state.in_(SHEET_STATES), ~Job.is_demo)
    ).all()
    for application in applications:
        queue_for_sheet(db, application)
    db.commit()
    return len(applications)


def waiting_count(db: Session) -> int:
    return db.scalar(
        select(func.count(func.distinct(SheetOutbox.application_id))).where(SheetOutbox.synced_at.is_(None))
    )


def check_connection(url: str) -> str:
    """Ask the user's script whether it is there. Returns "" when it is, else what is wrong."""
    try:
        answer = post_json(url, {"rows": []})
    except ValueError:
        return (
            "The link answered, but not the way the script should. In the script's deployment, check that "
            '"Who has access" is set to "Anyone", then copy the web app link again.'
        )
    except OSError as exc:
        return f"The link could not be reached ({exc}). Check your internet connection and the link."
    return "" if answer.get("ok") else f"The script refused the test: {answer.get('error', 'no reason given')}"


def sync_pending(db: Session) -> SyncResult:
    """Send everything waiting in the outbox. Never raises; what could not be sent stays queued."""
    url = db.get(AppSettings, 1).sheet_webhook_url
    if not is_apps_script_link(url):
        return SyncResult()

    pending = db.scalars(select(SheetOutbox).where(SheetOutbox.synced_at.is_(None)).order_by(SheetOutbox.id)).all()
    by_application: dict[int, list[SheetOutbox]] = {}
    for entry in pending:
        by_application.setdefault(entry.application_id, []).append(entry)
    if not by_application:
        return SyncResult()

    applications = db.scalars(
        select(Application).where(Application.id.in_(by_application)).options(joinedload(Application.job))
    ).all()
    role_names = dict(db.execute(select(SearchProfile.id, SearchProfile.role)).all())
    cv_names = dict(db.execute(select(CV.id, CV.original_name)).all())

    result = SyncResult()
    for start in range(0, len(applications), ROWS_PER_REQUEST):
        batch = applications[start : start + ROWS_PER_REQUEST]
        # An application that no longer belongs on the Sheet (now skipped, or a sample) is dropped from the queue.
        rows = [_row(a, role_names, cv_names) for a in batch if a.state in SHEET_STATES and not a.job.is_demo]
        entries = [entry for a in batch for entry in by_application[a.id]]
        try:
            if rows:
                answer = post_json(url, {"rows": rows})
                if not answer.get("ok"):
                    raise ValueError(str(answer.get("error", "the script gave no reason")))
        except (OSError, ValueError) as exc:
            result.error = f"Google Sheet could not be updated: {exc}"
            for entry in entries:
                entry.attempts += 1
                entry.last_error = str(exc)[:500]
            db.commit()
            log.warning("Sheet sync failed, %d rows stay queued: %s", len(rows), exc)
            break
        now = utcnow()
        for entry in entries:
            entry.synced_at = now
            entry.last_error = ""
        db.commit()
        result.sent += len(rows)
    if result.sent:
        log.info("Sheet sync: %d rows sent", result.sent)
    return result


def sync_in_background() -> None:
    """Off the request thread, so a slow or unreachable network never delays the dashboard."""

    def run() -> None:
        try:
            with SessionLocal() as db:
                sync_pending(db)
        except Exception:  # a background nicety must never take anything else down
            log.exception("Background sheet sync failed")

    threading.Thread(target=run, name="sheet-sync", daemon=True).start()


def _row(application: Application, role_names: dict[int, str], cv_names: dict[int, str]) -> dict:
    job = application.job
    return {
        "job_id": job.naukri_job_id,
        "applied_on": f"{to_local(application.applied_at):%Y-%m-%d %H:%M}" if application.applied_at else "",
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "experience": _range(job.experience_min, job.experience_max, "yrs"),
        "salary": _range(job.salary_min_lpa, job.salary_max_lpa, "LPA") or "Not disclosed",
        "skills": ", ".join(job.skills[:15]),
        "match_score": job.match_score if job.match_score is not None else "",
        "status": STATUS_ON_SHEET[application.state],
        "apply_link": job.company_apply_url,
        "naukri_link": job.url,
        "cv_used": cv_names.get(application.cv_id, ""),
        "role": role_names.get(job.search_profile_id, ""),
        "notes": application.notes,
        "updated_on": f"{to_local(application.updated_at):%Y-%m-%d %H:%M}",
    }


def _range(low: float | None, high: float | None, unit: str) -> str:
    if low is not None and high is not None:
        return f"{low:g}-{high:g} {unit}"
    if low is not None:
        return f"{low:g}+ {unit}"
    if high is not None:
        return f"Up to {high:g} {unit}"
    return ""
