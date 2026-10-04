from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.web import redirect, render
from backend.core.clock import start_of_local_day_utc
from backend.core.webhook import is_apps_script_link
from backend.db.database import get_db
from backend.db.models import CV, Application, ApplicationState, AppSettings, CandidateProfile, Job, SearchProfile

router = APIRouter()


@router.get("/")
def overview(request: Request, db: Session = Depends(get_db)):
    app_settings = db.get(AppSettings, 1)
    if not app_settings.onboarding_done:
        return redirect("/welcome")

    profile = db.get(CandidateProfile, 1)
    # Sample jobs are left out of every number on this page.
    by_state = dict(
        db.execute(
            select(Application.state, func.count()).join(Job).where(~Job.is_demo).group_by(Application.state)
        ).all()
    )
    applied_today = db.scalar(
        select(func.count()).select_from(Application).where(Application.applied_at >= start_of_local_day_utc())
    )
    checklist = [
        ("CV uploaded", bool(db.scalar(select(func.count()).select_from(CV).where(CV.is_active))), "/cv"),
        ("Profile has your name and skills", bool(profile.full_name and profile.skills), "/profile"),
        (
            "At least one role is switched on",
            bool(db.scalar(select(func.count()).select_from(SearchProfile).where(SearchProfile.is_active))),
            "/roles",
        ),
        ("Google Sheet connected", is_apps_script_link(app_settings.sheet_webhook_url), "/settings"),
        ("Naukri account connected", bool(app_settings.naukri_connected_at), "/settings"),
    ]
    return render(
        request,
        "overview.html",
        active="overview",
        name=profile.full_name.split()[0] if profile.full_name else "",
        jobs_found=sum(by_state.values()),
        queued=by_state.get(ApplicationState.QUEUED, 0),
        applied=by_state.get(ApplicationState.APPLIED, 0),
        applied_today=applied_today,
        daily_cap=app_settings.daily_apply_cap,
        needs_manual=by_state.get(ApplicationState.NEEDS_MANUAL, 0) + by_state.get(ApplicationState.EXTERNAL, 0),
        failed=by_state.get(ApplicationState.FAILED, 0),
        checklist=checklist,
    )
