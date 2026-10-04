from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.core.clock import utcnow


class Base(DeclarativeBase):
    pass


class ApplicationState(StrEnum):
    DISCOVERED = "discovered"
    SKIPPED = "skipped"
    QUEUED = "queued"
    APPLYING = "applying"
    APPLIED = "applied"
    FAILED = "failed"
    NEEDS_MANUAL = "needs_manual"
    EXTERNAL = "external"


class ApplyType(StrEnum):
    UNKNOWN = "unknown"
    DIRECT = "direct"
    QUESTIONNAIRE = "questionnaire"
    EXTERNAL = "external"


class ApplyMode(StrEnum):
    DRY_RUN = "dry_run"  # practice: open each job and report, but never click Apply
    REAL = "real"


class CandidateProfile(Base):
    """Single row (id=1)."""

    __tablename__ = "candidate_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    current_location: Mapped[str] = mapped_column(String(100), default="")
    experience_years: Mapped[float | None] = mapped_column(default=None)
    current_ctc_lpa: Mapped[float | None] = mapped_column(default=None)
    expected_ctc_lpa: Mapped[float | None] = mapped_column(default=None)
    notice_period_days: Mapped[int | None] = mapped_column(default=None)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    education: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class CV(Base):
    __tablename__ = "cvs"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(64), unique=True)
    uploaded_at: Mapped[datetime] = mapped_column(default=utcnow)
    parsed_text: Mapped[str] = mapped_column(Text, default="")
    parsed: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(default=False)


class SearchProfile(Base):
    """One role the user wants applied to. Experience comes from the candidate profile."""

    __tablename__ = "search_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(150))
    locations: Mapped[list[str]] = mapped_column(JSON, default=list)
    min_salary_lpa: Mapped[float | None] = mapped_column(default=None)
    max_job_age_days: Mapped[int] = mapped_column(default=7)
    exclude_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    exclude_companies: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Answer(Base):
    """Saved answer for a question recruiters ask during apply."""

    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(String(300))
    answer: Mapped[str] = mapped_column(String(500))


class AppSettings(Base):
    """Single row (id=1)."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    sheet_url: Mapped[str] = mapped_column(String(500), default="")
    # Web-app link of the small script the user adds to their own Sheet; rows are posted to it.
    # Anyone holding this link can add rows to that Sheet, so it is never shown outside Settings.
    sheet_webhook_url: Mapped[str] = mapped_column(String(500), default="")
    daily_apply_cap: Mapped[int] = mapped_column(default=20)
    min_match_score: Mapped[int] = mapped_column(default=60)
    # False until the first-run welcome setup is finished or skipped.
    onboarding_done: Mapped[bool] = mapped_column(default=False)
    # Registration with the tool's owner (name + email). Sent only after the user continued past
    # the welcome step that shows the notice; registered_at stays empty until it went through.
    apply_mode: Mapped[str] = mapped_column(String(20), default=ApplyMode.DRY_RUN)
    # When the user last logged in to Naukri in the tool's browser. Empty = not connected.
    naukri_connected_at: Mapped[datetime | None] = mapped_column(default=None)
    install_id: Mapped[str] = mapped_column(String(32), default="")
    registration_consent_at: Mapped[datetime | None] = mapped_column(default=None)
    registered_at: Mapped[datetime | None] = mapped_column(default=None)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    naukri_job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(300), default="")
    location: Mapped[str] = mapped_column(String(300), default="")
    experience_min: Mapped[int | None] = mapped_column(default=None)
    experience_max: Mapped[int | None] = mapped_column(default=None)
    salary_min_lpa: Mapped[float | None] = mapped_column(default=None)
    salary_max_lpa: Mapped[float | None] = mapped_column(default=None)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(600), default="")
    posted_on: Mapped[date | None] = mapped_column(default=None)
    apply_type: Mapped[str] = mapped_column(String(20), default=ApplyType.UNKNOWN)
    # For "apply on company site" jobs: the company's own link, read from the job page.
    company_apply_url: Mapped[str] = mapped_column(String(1000), default="")
    dedupe_key: Mapped[str] = mapped_column(String(400), default="", index=True)
    match_score: Mapped[int | None] = mapped_column(default=None)
    match_notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    search_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_profiles.id", ondelete="SET NULL"), default=None
    )
    discovered_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Sample job made up to show how matching works. Never applied to, never sent to the Sheet.
    is_demo: Mapped[bool] = mapped_column(default=False)

    application: Mapped["Application"] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )


class Application(Base):
    """Our attempt at one job. Exactly one per job, created when the job is discovered."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    state: Mapped[str] = mapped_column(String(20), default=ApplicationState.DISCOVERED, index=True)
    cv_id: Mapped[int | None] = mapped_column(ForeignKey("cvs.id", ondelete="SET NULL"), default=None)
    applied_at: Mapped[datetime | None] = mapped_column(default=None)
    naukri_status: Mapped[str] = mapped_column(String(100), default="")
    status_updated_at: Mapped[datetime | None] = mapped_column(default=None)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    job: Mapped[Job] = relationship(back_populates="application")


class SheetOutbox(Base):
    """An application row waiting to be pushed to Google Sheets."""

    __tablename__ = "sheet_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    synced_at: Mapped[datetime | None] = mapped_column(default=None)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    found: Mapped[int] = mapped_column(default=0)
    matched: Mapped[int] = mapped_column(default=0)
    applied: Mapped[int] = mapped_column(default=0)
    skipped: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)
    error: Mapped[str] = mapped_column(Text, default="")
