from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.web import FormError, optional_number, redirect, render, split_list
from backend.db.database import get_db
from backend.db.models import SearchProfile
from backend.services.ingest import rejudge_jobs

router = APIRouter(prefix="/roles")

JOB_AGE_CHOICES = [1, 3, 7, 15, 30]
# Salary is typed in lakhs per year. Anything above this was almost certainly typed in rupees
# (seen on the owner's first real role: 50000), and as a filter it rejects every job.
MAX_SALARY_LPA = 100


def _list_page(request: Request, db: Session, *, error: str = "", status_code: int = 200):
    return render(
        request,
        "roles.html",
        status_code=status_code,
        active="roles",
        error=error,
        roles=db.scalars(select(SearchProfile).order_by(SearchProfile.id)).all(),
        job_age_choices=JOB_AGE_CHOICES,
        max_salary=MAX_SALARY_LPA,
    )


def _edit_page(request: Request, role: SearchProfile, *, error: str = "", status_code: int = 200):
    return render(
        request,
        "role_edit.html",
        status_code=status_code,
        active="roles",
        error=error,
        role=role,
        job_age_choices=JOB_AGE_CHOICES,
    )


def _get_role(db: Session, role_id: int) -> SearchProfile:
    role = db.get(SearchProfile, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


def _apply_form(
    target: SearchProfile,
    role: str,
    locations: str,
    min_salary_lpa: str,
    max_job_age_days: str,
    exclude_keywords: str,
    exclude_companies: str,
) -> None:
    """Validate everything first so a bad value never leaves the role half-updated."""
    title = " ".join(role.split())
    if not title:
        raise FormError("Please type the job title you are looking for.")
    min_salary = optional_number(min_salary_lpa, float, "Lowest salary")
    if min_salary is not None and min_salary > MAX_SALARY_LPA:
        raise FormError(
            "Lowest salary is typed in lakhs per year, so that number is too big. "
            "For ₹50,000 a month, type 6. For ₹8,00,000 a year, type 8."
        )
    job_age = optional_number(max_job_age_days, int, "Job age")
    if job_age not in JOB_AGE_CHOICES:
        raise FormError("Please pick a job age from the list.")

    target.role = title[:150]
    target.locations = split_list(locations)
    target.min_salary_lpa = min_salary
    target.max_job_age_days = job_age
    target.exclude_keywords = split_list(exclude_keywords)
    target.exclude_companies = split_list(exclude_companies)


@router.get("")
def roles_page(request: Request, db: Session = Depends(get_db)):
    return _list_page(request, db)


@router.post("")
def add_role(
    request: Request,
    role: Annotated[str, Form()] = "",
    locations: Annotated[str, Form()] = "",
    min_salary_lpa: Annotated[str, Form()] = "",
    max_job_age_days: Annotated[str, Form()] = "7",
    exclude_keywords: Annotated[str, Form()] = "",
    exclude_companies: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    new_role = SearchProfile()
    try:
        _apply_form(new_role, role, locations, min_salary_lpa, max_job_age_days, exclude_keywords, exclude_companies)
    except FormError as exc:
        return _list_page(request, db, error=str(exc), status_code=400)
    db.add(new_role)
    db.commit()
    return redirect("/roles", "added")


@router.get("/{role_id}")
def edit_page(role_id: int, request: Request, db: Session = Depends(get_db)):
    return _edit_page(request, _get_role(db, role_id))


@router.post("/{role_id}")
def update_role(
    role_id: int,
    request: Request,
    role: Annotated[str, Form()] = "",
    locations: Annotated[str, Form()] = "",
    min_salary_lpa: Annotated[str, Form()] = "",
    max_job_age_days: Annotated[str, Form()] = "7",
    exclude_keywords: Annotated[str, Form()] = "",
    exclude_companies: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    target = _get_role(db, role_id)
    try:
        _apply_form(target, role, locations, min_salary_lpa, max_job_age_days, exclude_keywords, exclude_companies)
    except FormError as exc:
        return _edit_page(request, target, error=str(exc), status_code=400)
    db.commit()
    rejudge_jobs(db)
    return redirect("/roles", "saved")


@router.post("/{role_id}/toggle")
def toggle_role(role_id: int, db: Session = Depends(get_db)):
    role = _get_role(db, role_id)
    role.is_active = not role.is_active
    db.commit()
    rejudge_jobs(db)  # a switched-off role's jobs stop waiting to be applied to
    return redirect("/roles", "saved")


@router.post("/{role_id}/delete")
def delete_role(role_id: int, db: Session = Depends(get_db)):
    db.delete(_get_role(db, role_id))
    db.commit()
    return redirect("/roles", "deleted")
