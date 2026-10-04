"""The one door every job comes in through, whatever found it (Naukri search, demo data).

For each job: drop it if it is a duplicate, score it against the role it was found for, then
either queue it for applying or mark it skipped.
"""

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from backend.db.models import (
    Application,
    ApplicationState,
    AppSettings,
    ApplyType,
    CandidateProfile,
    Job,
    SearchProfile,
)
from backend.services.matching import score_job

log = logging.getLogger(__name__)

_NON_WORD = re.compile(r"[^a-z0-9]+")
_COMPANY_SUFFIXES = {"pvt", "private", "ltd", "limited", "inc", "llp", "llc", "corp", "corporation"}


@dataclass
class JobData:
    """A job as handed over by whatever found it."""

    naukri_job_id: str
    title: str
    company: str = ""
    location: str = ""
    experience_min: int | None = None
    experience_max: int | None = None
    salary_min_lpa: float | None = None
    salary_max_lpa: float | None = None
    skills: list[str] = field(default_factory=list)
    description: str = ""
    url: str = ""
    posted_on: date | None = None
    apply_type: str = ApplyType.UNKNOWN
    is_demo: bool = False


@dataclass
class IngestResult:
    added: int = 0
    duplicates: int = 0
    queued: int = 0
    manual: int = 0
    skipped: int = 0


def dedupe_key(company: str, title: str, location: str) -> str:
    """Same company + title + place is treated as the same job, even under a new Naukri ID.

    Recruiters repost jobs; without this the tool would apply to the same opening again.
    Empty when the company is unknown, because title + place alone is not enough to be sure.
    """
    company_words = [word for word in _NON_WORD.sub(" ", company.lower()).split() if word not in _COMPANY_SUFFIXES]
    if not company_words:
        return ""
    title_words = _NON_WORD.sub(" ", title.lower()).split()
    place_words = sorted(set(_NON_WORD.sub(" ", location.lower()).split()))
    return "|".join([" ".join(company_words), " ".join(title_words), " ".join(place_words)])


def ingest_jobs(db: Session, jobs: Iterable[JobData], role: SearchProfile) -> IngestResult:
    candidate = db.get(CandidateProfile, 1)
    threshold = db.get(AppSettings, 1).min_match_score
    result = IngestResult()

    for data in jobs:
        key = dedupe_key(data.company, data.title, data.location)
        same_job = Job.naukri_job_id == data.naukri_job_id
        if key:
            same_job = or_(same_job, Job.dedupe_key == key)
        if db.scalar(select(Job.id).where(same_job).limit(1)) is not None:
            result.duplicates += 1
            continue

        job = Job(**vars(data), dedupe_key=key, search_profile_id=role.id)
        # The link is shown as a clickable link, so only a plain web address is kept.
        if not job.url.startswith(("https://", "http://")):
            job.url = ""
        state = _judge(job, role, candidate, threshold)
        if state == ApplicationState.SKIPPED:
            result.skipped += 1
        elif state == ApplicationState.EXTERNAL:
            result.manual += 1
        else:
            result.queued += 1
        job.application = Application(state=state)
        db.add(job)
        db.flush()  # so the next job in this batch is checked against this one
        result.added += 1

    db.commit()
    log.info("Ingested for role %r: %s", role.role, result)
    return result


def _judge(job: Job, role: SearchProfile, candidate: CandidateProfile, threshold: int) -> ApplicationState:
    """Score the job, store the score and reasons on it, and say what should happen to it."""
    if not role.is_active:
        job.match_score = None
        job.match_notes = [f'The role "{role.role}" is switched off']
        return ApplicationState.SKIPPED
    match = score_job(job, role, candidate)
    # A job rejected by a filter has no score, only the reasons it was rejected.
    job.match_score = None if match.excluded else match.score
    job.match_notes = match.notes
    if match.excluded or match.score < threshold:
        return ApplicationState.SKIPPED
    if job.apply_type == ApplyType.EXTERNAL:
        return ApplicationState.EXTERNAL
    return ApplicationState.QUEUED


# States that only reflect matching. A job the tool has started on, applied to, or handed to
# the user keeps its state whatever the profile says later.
_REJUDGED_STATES = (ApplicationState.QUEUED, ApplicationState.SKIPPED, ApplicationState.EXTERNAL)


def rejudge_jobs(db: Session) -> None:
    """Match waiting and skipped jobs again. Call after the profile, a role or the cut-off changes."""
    candidate = db.get(CandidateProfile, 1)
    threshold = db.get(AppSettings, 1).min_match_score
    roles = {role.id: role for role in db.scalars(select(SearchProfile))}
    jobs = db.scalars(
        select(Job)
        .join(Application)
        .where(Application.state.in_(_REJUDGED_STATES), Job.search_profile_id.is_not(None))
        .options(joinedload(Job.application))
    ).all()
    for job in jobs:
        job.application.state = _judge(job, roles[job.search_profile_id], candidate, threshold)
    db.commit()
