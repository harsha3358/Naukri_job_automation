import io

import pytest
from docx import Document
from sqlalchemy import select

from backend.config import config
from backend.db.models import CV, Answer, Application, AppSettings, CandidateProfile, Job, SearchProfile

SHEET = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit#gid=0"


def docx_bytes(*lines: str) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def upload(client, url: str, name: str, data: bytes):
    return client.post(url, files={"file": (name, data, "application/octet-stream")})


# --- first run ---------------------------------------------------------------


def test_first_visit_goes_to_the_welcome_setup(client):
    response = client.get("/")
    assert response.status_code == 303
    assert response.headers["location"] == "/welcome"
    assert "Welcome to Naukri Job Automation" in client.get("/welcome").text


def test_welcome_setup_end_to_end(client, db):
    response = client.post(
        "/welcome",
        data={"full_name": "Ravi Kumar", "email": "ravi@example.com", "experience_years": "0", "current_location": "Hyderabad"},
    )
    assert response.headers["location"] == "/welcome/cv"
    assert "Nice to meet you, Ravi" in client.get("/welcome/cv").text

    cv = docx_bytes("Ravi Kumar", "Skills: React, JavaScript, HTML")
    assert upload(client, "/welcome/cv", "ravi.docx", cv).headers["location"] == "/welcome/role"

    response = client.post("/welcome/role", data={"role": "Frontend Developer", "locations": "Hyderabad, Remote"})
    assert response.headers["location"] == "/welcome/sheet"

    assert client.post("/welcome/sheet", data={"sheet_url": "https://example.com/sheet"}).status_code == 400
    assert client.post("/welcome/sheet", data={"sheet_url": SHEET}).headers["location"] == "/welcome/done"

    done = client.get("/welcome/done").text
    assert "You're set, Ravi" in done
    assert "Skipped" not in done

    assert client.post("/welcome/finish", data={"tour": "1"}).headers["location"] == "/?tour=1"
    home = client.get("/")
    assert home.status_code == 200
    assert "Hi Ravi" in home.text

    db.expire_all()
    profile = db.get(CandidateProfile, 1)
    assert (profile.full_name, profile.email, profile.experience_years) == ("Ravi Kumar", "ravi@example.com", 0.0)
    assert "React" in profile.skills
    role = db.scalars(select(SearchProfile)).one()
    assert (role.role, role.locations) == ("Frontend Developer", ["Hyderabad", "Remote"])
    assert db.get(AppSettings, 1).sheet_url == SHEET


def test_setup_can_be_skipped(client):
    assert client.post("/welcome/finish").headers["location"] == "/"
    home = client.get("/")
    assert home.status_code == 200
    assert "Do this" in home.text  # checklist shows what is still missing


def test_welcome_needs_a_name(client):
    assert client.post("/welcome", data={"full_name": "  "}).status_code == 400


def test_done_step_lists_what_was_skipped(client):
    assert client.get("/welcome/done").text.count("Skipped. Add it later") == 4


# --- pages -------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/cv", "/profile", "/roles", "/answers", "/jobs", "/settings"])
def test_every_page_opens(client, onboarded, path):
    assert client.get(path).status_code == 200


# --- CV ----------------------------------------------------------------------


def test_cv_upload_fills_only_empty_profile_fields(client, db, make_pdf):
    profile = db.get(CandidateProfile, 1)
    profile.full_name = "Name I Typed"
    db.commit()

    response = upload(client, "/cv/upload", "my cv.pdf", make_pdf("Asha Verma asha@example.com 9876543210 Python Django"))
    assert response.headers["location"] == "/cv?msg=cv_uploaded"

    db.expire_all()
    profile = db.get(CandidateProfile, 1)
    assert profile.full_name == "Name I Typed"
    assert profile.email == "asha@example.com"
    assert profile.phone == "9876543210"
    assert profile.skills == ["Python", "Django"]

    cv = db.scalars(select(CV)).one()
    assert cv.is_active
    assert cv.original_name == "my cv.pdf"
    assert (config.resumes_dir / cv.stored_name).exists()
    assert "Python" in client.get("/cv").text


@pytest.mark.parametrize(
    "name, data, message",
    [
        ("photo.jpg", b"hello", "PDF, DOCX or TXT"),
        ("cv.pdf", b"not really a pdf", "could not be opened"),
        ("cv.pdf", b"", "empty"),
        ("", b"", "PDF, DOCX or TXT"),  # form sent with no file chosen
    ],
)
def test_bad_cv_uploads_are_refused_with_a_reason(client, db, name, data, message):
    response = upload(client, "/cv/upload", name, data)
    assert response.status_code == 400
    assert message in response.text
    assert db.scalars(select(CV)).first() is None
    assert not any(config.resumes_dir.iterdir())


def test_cv_with_no_readable_text_is_refused(client, make_pdf):
    response = upload(client, "/cv/upload", "scan.pdf", make_pdf(""))
    assert response.status_code == 400
    assert "No text could be read" in response.text


def test_oversized_cv_is_refused(client):
    too_big = b"x" * (config.max_cv_size_mb * 1024 * 1024 + 1)
    response = upload(client, "/cv/upload", "cv.pdf", too_big)
    assert response.status_code == 400
    assert "larger than" in response.text


def test_newest_cv_is_active_and_deleting_it_falls_back(client, db):
    upload(client, "/cv/upload", "old.docx", docx_bytes("Old CV with Python"))
    upload(client, "/cv/upload", "new.docx", docx_bytes("New CV with Java"))
    old, new = db.scalars(select(CV).order_by(CV.id)).all()
    assert (old.is_active, new.is_active) == (False, True)
    new_file = config.resumes_dir / new.stored_name
    assert new_file.exists()

    client.post(f"/cv/{new.id}/delete")
    db.expire_all()
    remaining = db.scalars(select(CV)).one()
    assert remaining.original_name == "old.docx"
    assert remaining.is_active
    assert not new_file.exists()


def test_plain_text_cv_is_accepted(client, db):
    response = upload(client, "/cv/upload", "cv.txt", "Meena Rao\nSkills: Python, SQL".encode())
    assert response.status_code == 303
    assert db.get(CandidateProfile, 1).skills == ["Python", "SQL"]


def test_use_in_profile_overwrites_with_cv_details(client, db):
    profile = db.get(CandidateProfile, 1)
    profile.skills = ["Excel"]
    db.commit()
    upload(client, "/cv/upload", "cv.docx", docx_bytes("Skills: React, Node.js"))
    cv = db.scalars(select(CV)).one()

    db.expire_all()
    assert db.get(CandidateProfile, 1).skills == ["Excel"]  # upload alone does not overwrite
    client.post(f"/cv/{cv.id}/use-in-profile")
    db.expire_all()
    assert db.get(CandidateProfile, 1).skills == ["React", "Node.js"]


# --- profile, roles, answers, settings ---------------------------------------


def test_profile_saves_and_tidies_skills(client, db):
    response = client.post(
        "/profile",
        data={
            "full_name": "Ravi  Kumar",
            "experience_years": "1.5",
            "notice_period_days": "30",
            "expected_ctc_lpa": "",
            "skills": "reactjs, React, node js,  , Figma",
        },
    )
    assert response.headers["location"] == "/profile?msg=saved"
    db.expire_all()
    profile = db.get(CandidateProfile, 1)
    assert profile.full_name == "Ravi Kumar"
    assert profile.experience_years == 1.5
    assert profile.notice_period_days == 30
    assert profile.expected_ctc_lpa is None
    assert profile.skills == ["React", "Node.js", "Figma"]


@pytest.mark.parametrize("field, value", [("experience_years", "abc"), ("experience_years", "-1"), ("notice_period_days", "2.5")])
def test_profile_rejects_bad_numbers(client, field, value):
    assert client.post("/profile", data={field: value}).status_code == 400


def test_roles_add_edit_toggle_delete(client, db):
    assert client.post("/roles", data={"role": ""}).status_code == 400
    assert client.post("/roles", data={"role": "QA", "max_job_age_days": "5"}).status_code == 400

    client.post(
        "/roles",
        data={"role": "React Developer", "locations": "Pune, pune, Mumbai", "min_salary_lpa": "4.5", "max_job_age_days": "3"},
    )
    role = db.scalars(select(SearchProfile)).one()
    assert (role.role, role.locations, role.min_salary_lpa, role.max_job_age_days, role.is_active) == (
        "React Developer",
        ["Pune", "Mumbai"],
        4.5,
        3,
        True,
    )
    assert "React Developer" in client.get(f"/roles/{role.id}").text

    client.post(f"/roles/{role.id}", data={"role": "React Engineer", "max_job_age_days": "7", "exclude_keywords": "Senior, Lead"})
    client.post(f"/roles/{role.id}/toggle")
    db.expire_all()
    role = db.scalars(select(SearchProfile)).one()
    assert (role.role, role.locations, role.min_salary_lpa, role.exclude_keywords, role.is_active) == (
        "React Engineer",
        [],
        None,
        ["Senior", "Lead"],
        False,
    )

    client.post(f"/roles/{role.id}/delete")
    assert db.scalars(select(SearchProfile)).first() is None
    assert client.get(f"/roles/{role.id}").status_code == 404


def test_salary_typed_in_rupees_is_refused_with_an_example(client, db):
    response = client.post("/roles", data={"role": "AI Engineer", "min_salary_lpa": "50000", "max_job_age_days": "7"})
    assert response.status_code == 400
    assert "For ₹50,000 a month, type 6" in response.text
    assert db.scalars(select(SearchProfile)).first() is None


def test_jobs_page_says_why_each_job_was_skipped_and_what_to_change(client, db, onboarded):
    # The owner's first real setup: salary typed in rupees, no skills in the profile.
    role = SearchProfile(role="AI Engineer", locations=["Hyderabad"], min_salary_lpa=50000)
    db.add(role)
    db.commit()
    low_pay = Job(
        naukri_job_id="1", title="AI Engineer", url="https://www.naukri.com/job-listings-1", search_profile_id=role.id,
        match_score=None, match_notes=["Salary: up to 8 LPA is below your lowest of 50000 LPA"],
    )
    weak = Job(
        naukri_job_id="2", title="Software Engineer", url="https://www.naukri.com/job-listings-2", search_profile_id=role.id,
        match_score=44, match_notes=["Title: 1 of 2 role words found"],
    )
    low_pay.application = Application(state="skipped")
    weak.application = Application(state="skipped")
    db.add_all([low_pay, weak])
    db.commit()

    page = client.get("/jobs").text
    assert "Why jobs were skipped" in page
    assert "<strong>1</strong> Salary below your lowest" in page
    assert "<strong>1</strong> Match score below your cut-off" in page
    assert "Salary: up to 8 LPA is below your lowest of 50000 LPA" in page
    assert "Match 44 is below your cut-off of 60" in page
    assert "is 50000 lakhs a year, which rejects almost every job" in page
    assert "Your profile has no skills" in page
    assert page.count(">Open on Naukri</a>") == 2

    assert "This is in lakhs per year, so it rejects almost every job" in client.get("/roles").text


def test_answers_add_and_delete(client, db):
    assert client.post("/answers", data={"question": "Relocate?", "answer": ""}).status_code == 400
    client.post("/answers", data={"question": "Are you willing to relocate?", "answer": "Yes"})
    answer = db.scalars(select(Answer)).one()
    assert "Are you willing to relocate?" in client.get("/answers").text
    client.post(f"/answers/{answer.id}/delete")
    assert db.scalars(select(Answer)).first() is None


def test_settings_save_and_limits(client, db):
    ok = {"sheet_url": SHEET, "daily_apply_cap": "15", "min_match_score": "70"}
    assert client.post("/settings", data=ok).headers["location"] == "/settings?msg=saved"
    db.expire_all()
    saved = db.get(AppSettings, 1)
    assert (saved.sheet_url, saved.daily_apply_cap, saved.min_match_score) == (SHEET, 15, 70)

    for bad in (
        {**ok, "daily_apply_cap": "51"},
        {**ok, "daily_apply_cap": "0"},
        {**ok, "min_match_score": "101"},
        {**ok, "sheet_url": "https://example.com/not-a-sheet"},
    ):
        assert client.post("/settings", data=bad).status_code == 400
    db.expire_all()
    assert db.get(AppSettings, 1).daily_apply_cap == 15


# --- jobs --------------------------------------------------------------------


def test_stored_job_is_listed_with_its_state(client, db):
    job = Job(naukri_job_id="abc123", title="Frontend Developer", company="Acme Tech", location="Hyderabad", match_score=82)
    job.application = Application()
    db.add(job)
    db.commit()

    page = client.get("/jobs").text
    assert "Frontend Developer" in page
    assert "Acme Tech" in page
    assert "82" in page
    assert "Found" in page


def test_deleting_a_job_removes_its_application(db):
    job = Job(naukri_job_id="abc123", title="Frontend Developer")
    job.application = Application()
    db.add(job)
    db.commit()
    db.delete(job)
    db.commit()
    assert db.scalars(select(Application)).first() is None


# --- local-only protection ---------------------------------------------------


def test_cross_site_form_posts_are_blocked(client, db):
    response = client.post("/settings", data={"daily_apply_cap": "50", "min_match_score": "0"}, headers={"origin": "https://evil.example"})
    assert response.status_code == 403
    assert db.get(AppSettings, 1).daily_apply_cap == 20


def test_same_origin_posts_are_allowed(client):
    response = client.post("/answers", data={"question": "Q", "answer": "A"}, headers={"origin": "http://127.0.0.1:8000"})
    assert response.status_code == 303


def test_foreign_host_header_is_rejected(client):
    assert client.get("/welcome", headers={"host": "evil.example"}).status_code == 400
