from collections import Counter

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.api.roles import MAX_SALARY_LPA
from backend.api.web import redirect, render
from backend.core.clock import start_of_local_day_utc
from backend.db.database import get_db
from backend.db.models import (
    Application,
    ApplicationState,
    ApplyMode,
    AppSettings,
    CandidateProfile,
    Job,
    Run,
    SearchProfile,
)
from backend.services.demo_jobs import load_demo_jobs, remove_demo_jobs
from backend.workers import runner
from backend.workers.apply import RUN_KIND as APPLY_RUN_KIND
from backend.workers.discover import RUN_KIND

router = APIRouter(prefix="/jobs")

PAGE_SIZE = 200

# How a filter's note starts -> the plain name of that reason in the summary.
_FILTER_REASONS = [
    ("Salary", "Salary below your lowest"),
    ("Location", "Not in your cities"),
    ("Experience", "Needs more experience than you have"),
    ("Posted", "Posted too long ago"),
    ("Title contains", "Has a word you chose to skip"),
    ("The role", "Its role is switched off"),
]


def skip_reason(job: Job, cut_off: int) -> tuple[str, str]:
    """Why a skipped job was skipped: (short group name for the summary, full sentence for the row)."""
    if job.match_score is not None:
        return "Match score below your cut-off", f"Match {job.match_score} is below your cut-off of {cut_off}"
    note = job.match_notes[0] if job.match_notes else "No reason was recorded"
    for start, group in _FILTER_REASONS:
        if note.startswith(start):
            return group, note
    return "From a company you chose to skip", note


def _tips(db: Session, groups: Counter, cut_off: int) -> list[str]:
    """What the user can change so fewer jobs are skipped."""
    tips: list[str] = []
    for role in db.scalars(select(SearchProfile).where(SearchProfile.min_salary_lpa > MAX_SALARY_LPA)):
        tips.append(
            f'The lowest salary on your role "{role.role}" is {role.min_salary_lpa:g} lakhs a year, which rejects '
            "almost every job. Salary is typed in lakhs per year: for ₹50,000 a month, type 6. Fix it on the Roles page."
        )
    if not db.get(CandidateProfile, 1).skills:
        tips.append(
            "Your profile has no skills, so jobs are judged on title and experience alone and few can pass. "
            "Upload your CV on the CV page, or type your skills on the Profile page."
        )
    elif groups["Match score below your cut-off"]:
        tips.append(
            f"Your cut-off is {cut_off}. You can lower it on the Settings page, or add another role "
            "whose title is closer to the jobs you want."
        )
    return tips


@router.get("")
def jobs_page(request: Request, db: Session = Depends(get_db)):
    jobs = db.scalars(
        select(Job)
        .options(joinedload(Job.application))
        .order_by(Job.match_score.desc().nulls_last(), Job.discovered_at.desc())
        .limit(PAGE_SIZE)
    ).all()
    app_settings = db.get(AppSettings, 1)
    cut_off = app_settings.min_match_score
    applied_today = db.scalar(
        select(func.count()).select_from(Application).where(Application.applied_at >= start_of_local_day_utc())
    )
    reasons = {job.id: skip_reason(job, cut_off) for job in jobs if job.application.state == ApplicationState.SKIPPED}
    # The summary counts real jobs only; sample jobs still show their own reason in the table.
    sample_ids = {job.id for job in jobs if job.is_demo}
    groups = Counter(group for job_id, (group, _) in reasons.items() if job_id not in sample_ids)
    return render(
        request,
        "jobs.html",
        active="jobs",
        jobs=jobs,
        skip_sentences={job_id: sentence for job_id, (_, sentence) in reasons.items()},
        skip_groups=groups.most_common(),
        tips=_tips(db, groups, cut_off) if groups else [],
        has_demo=bool(db.scalar(select(func.count()).select_from(Job).where(Job.is_demo))),
        searching=runner.current() == "search",
        applying=runner.current() == "apply",
        waiting=sum(1 for job in jobs if job.application.state == ApplicationState.QUEUED and not job.is_demo),
        connected=bool(app_settings.naukri_connected_at),
        real_mode=app_settings.apply_mode == ApplyMode.REAL,
        left_today=max(0, app_settings.daily_apply_cap - applied_today),
        last_search=_last_run(db, RUN_KIND),
        last_apply=_last_run(db, APPLY_RUN_KIND),
    )


def _last_run(db: Session, kind: str) -> Run | None:
    return db.scalars(
        select(Run).where(Run.kind == kind, Run.finished_at.is_not(None)).order_by(Run.id.desc()).limit(1)
    ).first()


@router.post("/demo")
def load_demo(db: Session = Depends(get_db)):
    role = db.scalars(select(SearchProfile).where(SearchProfile.is_active).order_by(SearchProfile.id)).first()
    if role is None:
        return redirect("/jobs", "demo_needs_role")
    load_demo_jobs(db, role)
    return redirect("/jobs", "demo_loaded")


@router.post("/demo/remove")
def remove_demo(db: Session = Depends(get_db)):
    remove_demo_jobs(db)
    return redirect("/jobs", "demo_removed")
