"""First-run setup: a few short steps, each of which can be skipped."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.web import FormError, optional_number, read_upload, redirect, render, split_list
from backend.config import config
from backend.db.database import get_db
from backend.db.models import CV, AppSettings, CandidateProfile, SearchProfile
from backend.services import registration
from backend.services.cv_parser import CVReadError
from backend.services.cv_store import store_cv
from backend.services.sheets_sync import sheet_id_from_url

router = APIRouter(prefix="/welcome")

STEPS = ["you", "cv", "role", "sheet", "done"]
STEP_URLS = {"you": "/welcome", "cv": "/welcome/cv", "role": "/welcome/role", "sheet": "/welcome/sheet"}


def _step(request: Request, db: Session, step: str, *, error: str = "", status_code: int = 200, typed_sheet_url: str = ""):
    profile = db.get(CandidateProfile, 1)
    app_settings = db.get(AppSettings, 1)
    position = STEPS.index(step)
    return render(
        request,
        "welcome.html",
        status_code=status_code,
        step=step,
        step_number=position + 1,
        step_count=len(STEPS),
        back_url=STEP_URLS[STEPS[position - 1]] if position else "",
        registration_on=config.registration_enabled,
        error=error,
        profile=profile,
        first_name=profile.full_name.split()[0] if profile.full_name else "",
        cv=db.scalars(select(CV).where(CV.is_active)).first(),
        roles=db.scalars(select(SearchProfile).order_by(SearchProfile.id)).all(),
        app_settings=app_settings,
        # After a rejected link, show what was typed so it can be corrected instead of retyped.
        sheet_url=typed_sheet_url or app_settings.sheet_url,
    )


@router.get("")
def step_you(request: Request, db: Session = Depends(get_db)):
    return _step(request, db, "you")


@router.post("")
def save_you(
    request: Request,
    full_name: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    experience_years: Annotated[str, Form()] = "",
    current_location: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    profile = db.get(CandidateProfile, 1)
    email = email.strip()
    try:
        if not full_name.strip():
            raise FormError("Please type your name, or use Skip setup.")
        if config.registration_enabled and not email:
            raise FormError("Please type your email, or use Skip setup.")
        if email and "@" not in email:
            raise FormError("That email address does not look right.")
        experience = optional_number(experience_years, float, "Experience", maximum=50)
    except FormError as exc:
        return _step(request, db, "you", error=str(exc), status_code=400)
    profile.full_name = " ".join(full_name.split())[:200]
    profile.current_location = current_location.strip()[:100]
    if email:
        profile.email = email[:200]
    if experience is not None:
        profile.experience_years = experience
    db.commit()
    if config.registration_enabled:
        # The page they just submitted said their name and email would be sent.
        registration.record_consent(db)
        registration.send_pending_in_background()
    return redirect("/welcome/cv")


@router.get("/cv")
def step_cv(request: Request, db: Session = Depends(get_db)):
    return _step(request, db, "cv")


@router.post("/cv")
def save_cv(request: Request, file: UploadFile | None = None, db: Session = Depends(get_db)):
    try:
        store_cv(db, *read_upload(file))
    except CVReadError as exc:
        return _step(request, db, "cv", error=str(exc), status_code=400)
    return redirect("/welcome/role")


@router.get("/role")
def step_role(request: Request, db: Session = Depends(get_db)):
    return _step(request, db, "role")


@router.post("/role")
def save_role(
    request: Request,
    role: Annotated[str, Form()] = "",
    locations: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    if not role.strip():
        return _step(request, db, "role", error="Please type a job title, or skip this step.", status_code=400)
    db.add(SearchProfile(role=" ".join(role.split())[:150], locations=split_list(locations)))
    db.commit()
    return redirect("/welcome/sheet")


@router.get("/sheet")
def step_sheet(request: Request, db: Session = Depends(get_db)):
    return _step(request, db, "sheet")


@router.post("/sheet")
def save_sheet(request: Request, sheet_url: Annotated[str, Form()] = "", db: Session = Depends(get_db)):
    url = sheet_url.strip()
    if not sheet_id_from_url(url):
        return _step(
            request,
            db,
            "sheet",
            error="That does not look like a Google Sheets link. It should start with https://docs.google.com/spreadsheets/d/",
            status_code=400,
            typed_sheet_url=url,
        )
    db.get(AppSettings, 1).sheet_url = url
    db.commit()
    return redirect("/welcome/done")


@router.get("/done")
def step_done(request: Request, db: Session = Depends(get_db)):
    return _step(request, db, "done")


@router.post("/finish")
def finish(tour: Annotated[str, Form()] = "", db: Session = Depends(get_db)):
    """Ends setup, whether it was completed or skipped. The overview shows anything still missing."""
    db.get(AppSettings, 1).onboarding_done = True
    db.commit()
    return redirect("/?tour=1" if tour else "/")
