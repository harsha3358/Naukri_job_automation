from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from backend.api.web import FormError, optional_number, redirect, render, split_list
from backend.db.database import get_db
from backend.db.models import CandidateProfile
from backend.services.ingest import rejudge_jobs
from backend.services.skills import canonical_skill

router = APIRouter(prefix="/profile")


def _page(request: Request, db: Session, *, error: str = "", status_code: int = 200):
    return render(
        request,
        "profile.html",
        status_code=status_code,
        active="profile",
        error=error,
        profile=db.get(CandidateProfile, 1),
    )


@router.get("")
def profile_page(request: Request, db: Session = Depends(get_db)):
    return _page(request, db)


@router.post("")
def save_profile(
    request: Request,
    full_name: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    current_location: Annotated[str, Form()] = "",
    experience_years: Annotated[str, Form()] = "",
    current_ctc_lpa: Annotated[str, Form()] = "",
    expected_ctc_lpa: Annotated[str, Form()] = "",
    notice_period_days: Annotated[str, Form()] = "",
    skills: Annotated[str, Form()] = "",
    education: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    try:
        experience = optional_number(experience_years, float, "Experience", maximum=50)
        current_ctc = optional_number(current_ctc_lpa, float, "Current salary")
        expected_ctc = optional_number(expected_ctc_lpa, float, "Expected salary")
        notice = optional_number(notice_period_days, int, "Notice period", maximum=365)
    except FormError as exc:
        return _page(request, db, error=str(exc), status_code=400)

    profile = db.get(CandidateProfile, 1)
    profile.full_name = " ".join(full_name.split())[:200]
    profile.email = email.strip()[:200]
    profile.phone = phone.strip()[:30]
    profile.current_location = current_location.strip()[:100]
    profile.experience_years = experience
    profile.current_ctc_lpa = current_ctc
    profile.expected_ctc_lpa = expected_ctc
    profile.notice_period_days = notice
    # Store one spelling per skill so "reactjs" and "React" do not both appear.
    profile.skills = split_list(",".join(canonical_skill(skill) for skill in split_list(skills)))
    profile.education = education.strip()
    db.commit()
    rejudge_jobs(db)  # skills or experience may have changed
    return redirect("/profile", "saved")
