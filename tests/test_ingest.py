from datetime import date

import pytest
from sqlalchemy import select

from backend.db.models import Application, ApplicationState, ApplyType, CandidateProfile, Job, SearchProfile
from backend.services.demo_jobs import load_demo_jobs, remove_demo_jobs
from backend.services.ingest import JobData, dedupe_key, ingest_jobs


@pytest.fixture
def role(db) -> SearchProfile:
    profile = db.get(CandidateProfile, 1)
    profile.experience_years = 0.0
    profile.skills = ["React", "JavaScript", "HTML", "CSS"]
    role = SearchProfile(role="Frontend Developer", locations=["Hyderabad"])
    db.add(role)
    db.commit()
    return role


def job(job_id: str, **overrides) -> JobData:
    values = dict(
        naukri_job_id=job_id,
        title="Frontend Developer",
        company=f"Company {job_id}",
        location="Hyderabad",
        experience_min=0,
        experience_max=2,
        skills=["React", "JavaScript"],
        posted_on=date.today(),
        apply_type=ApplyType.DIRECT,
    )
    values.update(overrides)
    return JobData(**values)


def states(db) -> dict[str, str]:
    rows = db.execute(select(Job.naukri_job_id, Application.state).join(Application)).all()
    return dict(rows)


def test_matching_jobs_are_queued_and_others_skipped(db, role):
    result = ingest_jobs(db, [job("a"), job("b", title="Accountant", skills=["Tally"]), job("c", location="Pune")], role)

    assert (result.added, result.queued, result.skipped, result.duplicates) == (3, 1, 2, 0)
    assert states(db) == {"a": ApplicationState.QUEUED, "b": ApplicationState.SKIPPED, "c": ApplicationState.SKIPPED}
    stored = db.scalars(select(Job).where(Job.naukri_job_id == "a")).one()
    assert stored.match_score == 100
    assert stored.search_profile_id == role.id
    assert any(note.startswith("Skills: 2 of 2") for note in stored.match_notes)


def test_company_site_jobs_are_set_aside_for_the_user(db, role):
    result = ingest_jobs(db, [job("a", apply_type=ApplyType.EXTERNAL)], role)
    assert result.manual == 1
    assert states(db) == {"a": ApplicationState.EXTERNAL}


def test_the_same_job_id_is_never_stored_twice(db, role):
    ingest_jobs(db, [job("a")], role)
    result = ingest_jobs(db, [job("a", title="Changed title")], role)
    assert (result.added, result.duplicates) == (0, 1)
    assert len(db.scalars(select(Job)).all()) == 1
    assert len(db.scalars(select(Application)).all()) == 1


def test_a_repost_under_a_new_id_is_treated_as_a_duplicate(db, role):
    first = job("a", company="Acme Tech Pvt. Ltd.", location="Hyderabad, Pune")
    repost = job("b", company="ACME TECH", location="Pune / Hyderabad")
    result = ingest_jobs(db, [first, repost], role)  # also covers a duplicate inside one batch
    assert (result.added, result.duplicates) == (1, 1)


def test_same_title_at_a_different_company_is_not_a_duplicate(db, role):
    result = ingest_jobs(db, [job("a", company="Acme"), job("b", company="Globex")], role)
    assert result.added == 2


def test_jobs_without_a_company_are_only_deduplicated_by_id(db, role):
    assert dedupe_key("", "Frontend Developer", "Hyderabad") == ""
    result = ingest_jobs(db, [job("a", company=""), job("b", company="")], role)
    assert result.added == 2


def test_changing_the_cut_off_profile_or_role_rejudges_waiting_jobs(client, db, role):
    weak = job("weak", title="Developer", skills=["React", "Java", "Docker", "AWS"])  # scores under 60
    ingest_jobs(db, [job("good"), weak, job("done")], role)
    done = db.scalars(select(Application).join(Job).where(Job.naukri_job_id == "done")).one()
    done.state = ApplicationState.APPLIED
    db.commit()
    assert states(db)["weak"] == ApplicationState.SKIPPED

    # lower cut-off: the weak job now qualifies
    client.post("/settings", data={"daily_apply_cap": "20", "min_match_score": "30"})
    db.expire_all()
    assert states(db) == {"good": ApplicationState.QUEUED, "weak": ApplicationState.QUEUED, "done": ApplicationState.APPLIED}

    # profile loses its skills match: scores are recalculated, not kept from before
    before = db.scalars(select(Job).where(Job.naukri_job_id == "good")).one().match_score
    client.post("/profile", data={"experience_years": "0", "skills": "Tally"})
    db.expire_all()
    assert db.scalars(select(Job).where(Job.naukri_job_id == "good")).one().match_score < before

    # role switched off: nothing of it waits any more, but what was applied stays applied
    client.post(f"/roles/{role.id}/toggle")
    db.expire_all()
    assert states(db) == {"good": ApplicationState.SKIPPED, "weak": ApplicationState.SKIPPED, "done": ApplicationState.APPLIED}
    assert db.scalars(select(Job).where(Job.naukri_job_id == "good")).one().match_notes == ['The role "Frontend Developer" is switched off']

    client.post(f"/roles/{role.id}/toggle")
    client.post("/profile", data={"experience_years": "0", "skills": "React, JavaScript, HTML, CSS"})
    db.expire_all()
    assert states(db)["good"] == ApplicationState.QUEUED


def test_only_web_links_are_kept(db, role):
    ingest_jobs(db, [job("a", url="javascript:alert(1)"), job("b", url="https://www.naukri.com/job-listings-b")], role)
    urls = dict(db.execute(select(Job.naukri_job_id, Job.url)).all())
    assert urls == {"a": "", "b": "https://www.naukri.com/job-listings-b"}


def test_sample_jobs_show_each_outcome_and_are_removable(db, role):
    result = load_demo_jobs(db, role)

    assert (result.added, result.duplicates) == (7, 1)
    assert states(db) == {
        "demo-1": ApplicationState.QUEUED,  # fits
        "demo-2": ApplicationState.QUEUED,  # fits, fewer skills
        "demo-3": ApplicationState.SKIPPED,  # other city
        "demo-4": ApplicationState.SKIPPED,  # needs far more experience
        "demo-5": ApplicationState.SKIPPED,  # unrelated job
        "demo-7": ApplicationState.EXTERNAL,  # company-site apply
        "demo-8": ApplicationState.SKIPPED,  # old posting
    }
    scores = dict(db.execute(select(Job.naukri_job_id, Job.match_score)).all())
    assert scores["demo-1"] > scores["demo-2"] > scores["demo-5"]
    assert scores["demo-3"] is None  # filtered out, so it has reasons instead of a score
    other_city = db.scalars(select(Job).where(Job.naukri_job_id == "demo-3")).one()
    assert other_city.match_notes == ["Location: Guwahati is not one of your cities"]
    assert all(found.is_demo for found in db.scalars(select(Job)))

    load_demo_jobs(db, role)  # loading again replaces, never piles up
    assert len(db.scalars(select(Job)).all()) == 7

    remove_demo_jobs(db)
    assert db.scalars(select(Job)).first() is None
    assert db.scalars(select(Application)).first() is None


def test_sample_jobs_are_left_out_of_the_overview_numbers(client, db, role, onboarded):
    assert client.post("/jobs/demo").headers["location"] == "/jobs?msg=demo_loaded"
    jobs_page = client.get("/jobs").text
    assert "Demo Company A" in jobs_page
    assert "Remove sample jobs" in jobs_page

    overview = client.get("/").text
    assert '<span class="tile-value">0</span><span class="tile-label">Jobs found</span>' in overview

    assert client.post("/jobs/demo/remove").headers["location"] == "/jobs?msg=demo_removed"
    assert "Demo Company A" not in client.get("/jobs").text


def test_sample_jobs_need_a_role(client, db):
    assert client.post("/jobs/demo").headers["location"] == "/jobs?msg=demo_needs_role"
    assert db.scalars(select(Job)).first() is None
