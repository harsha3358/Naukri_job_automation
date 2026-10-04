from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from backend.api.web import FormError, optional_number, redirect, render
from backend.config import PROJECT_ROOT
from backend.core.webhook import is_apps_script_link
from backend.db.database import get_db
from backend.db.models import ApplyMode, AppSettings
from backend.services.ingest import rejudge_jobs
from backend.services.sheets_sync import (
    check_connection,
    queue_everything,
    sheet_id_from_url,
    sync_pending,
    waiting_count,
)
from backend.workers import runner

router = APIRouter(prefix="/settings")

# Our own ceiling. Applying in bulk is what gets Naukri accounts restricted.
MAX_DAILY_APPLY_CAP = 50
SHEET_SCRIPT = PROJECT_ROOT / "sheets" / "applications_sheet.gs"


def _page(request: Request, db: Session, *, error: str = "", status_code: int = 200, typed_connection: str | None = None):
    app_settings = db.get(AppSettings, 1)
    return render(
        request,
        "settings.html",
        status_code=status_code,
        active="settings",
        error=error,
        app_settings=app_settings,
        sheet_id=sheet_id_from_url(app_settings.sheet_url),
        sheet_connected=is_apps_script_link(app_settings.sheet_webhook_url),
        # After a rejected link, show what was typed so it can be corrected instead of pasted again.
        connection_link=app_settings.sheet_webhook_url if typed_connection is None else typed_connection,
        sheet_waiting=waiting_count(db),
        sheet_script=SHEET_SCRIPT.read_text(encoding="utf-8"),
        max_cap=MAX_DAILY_APPLY_CAP,
        connecting=runner.current() == "connect",
    )


@router.get("")
def settings_page(request: Request, db: Session = Depends(get_db)):
    return _page(request, db)


@router.post("")
def save_settings(
    request: Request,
    sheet_url: Annotated[str, Form()] = "",
    sheet_webhook_url: Annotated[str, Form()] = "",
    daily_apply_cap: Annotated[str, Form()] = "",
    min_match_score: Annotated[str, Form()] = "",
    apply_mode: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    app_settings = db.get(AppSettings, 1)
    url = sheet_url.strip()
    connection = sheet_webhook_url.strip()
    newly_connected = bool(connection) and connection != app_settings.sheet_webhook_url
    try:
        if url and not sheet_id_from_url(url):
            raise FormError(
                "That does not look like a Google Sheets link. It should start with "
                "https://docs.google.com/spreadsheets/d/"
            )
        if connection and not is_apps_script_link(connection):
            raise FormError(
                "That is not the web app link of the script. It starts with "
                "https://script.google.com/macros/s/ and ends with /exec"
            )
        cap = optional_number(daily_apply_cap, int, "Daily apply limit", maximum=MAX_DAILY_APPLY_CAP)
        score = optional_number(min_match_score, int, "Minimum match score", maximum=100)
        if not cap:
            raise FormError("Daily apply limit must be at least 1.")
        if score is None:
            raise FormError("Please enter a minimum match score.")
        if apply_mode and apply_mode not in set(ApplyMode):
            raise FormError("Please choose practice run or real applications.")
        if newly_connected:
            # Checked last, so a typo elsewhere on the form does not cost a trip to Google first.
            problem = check_connection(connection)
            if problem:
                raise FormError(problem)
    except FormError as exc:
        return _page(request, db, error=str(exc), status_code=400, typed_connection=connection)

    app_settings.sheet_url = url
    app_settings.sheet_webhook_url = connection
    app_settings.daily_apply_cap = cap
    app_settings.min_match_score = score
    if apply_mode:  # left as it is when the form did not send it
        app_settings.apply_mode = apply_mode
    db.commit()
    rejudge_jobs(db)  # the cut-off may have moved
    if newly_connected:
        queue_everything(db)  # applications made before the Sheet was connected go over now
        result = sync_pending(db)
        if result.error:
            return _page(request, db, error=result.error, status_code=502)
        return redirect("/settings", "sheet_connected")
    return redirect("/settings", "saved")


@router.post("/sheet/sync")
def send_to_sheet(request: Request, db: Session = Depends(get_db)):
    """Send every application to the Sheet again. Safe to repeat: the Sheet keeps one row per job."""
    if not is_apps_script_link(db.get(AppSettings, 1).sheet_webhook_url):
        return _page(request, db, error="Connect your Sheet first: paste the connection link and save.", status_code=400)
    queue_everything(db)
    result = sync_pending(db)
    if result.error:
        return _page(request, db, error=result.error, status_code=502)
    return redirect("/settings", "sheet_sent")
