"""Made-up jobs, built around the user's own role and skills, to show how matching works.

They are flagged is_demo: never applied to, never written to the Google Sheet.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import ApplyType, CandidateProfile, Job, SearchProfile
from backend.services.ingest import IngestResult, JobData, ingest_jobs

_UNRELATED_SKILLS = ["SAP", "AutoCAD", "Salesforce", "Tally"]


def build_demo_jobs(role: SearchProfile, candidate: CandidateProfile, today: date) -> list[JobData]:
    title = role.role
    city = role.locations[0] if role.locations else (candidate.current_location or "Hyderabad")
    other_city = "Guwahati" if city.lower() != "guwahati" else "Indore"
    years = int(candidate.experience_years or 0)
    my_skills = (candidate.skills or [])[:6]
    few_of_my_skills = my_skills[:2] + _UNRELATED_SKILLS

    def job(number: int, job_title: str, company: str, **overrides) -> JobData:
        values = dict(
            naukri_job_id=f"demo-{number}",
            title=job_title,
            company=company,
            location=city,
            experience_min=years,
            experience_max=years + 2,
            skills=my_skills,
            posted_on=today - timedelta(days=1),
            apply_type=ApplyType.DIRECT,
            is_demo=True,
        )
        values.update(overrides)
        return JobData(**values)

    return [
        job(1, title, "Demo Company A"),
        job(2, f"Junior {title}", "Demo Company B", skills=few_of_my_skills),
        job(3, title, "Demo Company C", location=other_city),
        job(4, f"Lead {title}", "Demo Company D", experience_min=years + 5, experience_max=years + 8),
        job(5, "Hospital Billing Executive", "Demo Company E", skills=["Medical Billing", "Tally"]),
        # Same company, title and city as the first one under a new ID: a repost, so it is ignored.
        job(6, title, "Demo Company A Pvt Ltd"),
        job(7, title, "Demo Company F", apply_type=ApplyType.EXTERNAL),
        job(8, title, "Demo Company G", posted_on=today - timedelta(days=45)),
    ]


def load_demo_jobs(db: Session, role: SearchProfile) -> IngestResult:
    remove_demo_jobs(db)
    return ingest_jobs(db, build_demo_jobs(role, db.get(CandidateProfile, 1), date.today()), role)


def remove_demo_jobs(db: Session) -> None:
    # One by one through the session, so each job's application is removed with it and the
    # session does not keep stale copies of rows whose ids are about to be reused.
    for job in db.scalars(select(Job).where(Job.is_demo)):
        db.delete(job)
    db.commit()
