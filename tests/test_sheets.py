"""Copying applications to the user's Google Sheet, with Google itself replaced by a stand-in."""

import pytest
from sqlalchemy import select

from backend.core.clock import utcnow
from backend.core.webhook import is_apps_script_link
from backend.db.models import (
    CV,
    Application,
    ApplicationState,
    AppSettings,
    ApplyType,
    Job,
    SearchProfile,
    SheetOutbox,
)
from backend.services import sheets_sync

SHEET = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit"
CONNECTION = "https://script.google.com/macros/s/AKfycbTESTONLY/exec"
SETTINGS = {"sheet_url": SHEET, "daily_apply_cap": "20", "min_match_score": "60"}


@pytest.fixture
def google(monkeypatch):
    """Stands in for the user's script. `google.posts` holds every batch of rows it was sent."""

    class Google:
        posts: list[list[dict]] = []
        failure: Exception | None = None
        answer: dict = {"ok": True}

        def post(self, url, payload):
            assert url == CONNECTION
            if self.failure:
                raise self.failure
            self.posts.append(payload["rows"])
            return self.answer

    stand_in = Google()
    stand_in.posts = []
    monkeypatch.setattr(sheets_sync, "post_json", stand_in.post)
    return stand_in


@pytest.fixture
def role(db) -> SearchProfile:
    role = SearchProfile(role="AI Engineer", locations=["Hyderabad"])
    db.add(role)
    db.commit()
    return role


def add_application(db, role, job_id: str, state: str, **job_fields) -> Application:
    job = Job(naukri_job_id=job_id, title="AI Engineer", company="Acme", url=f"https://www.naukri.com/job-listings-{job_id}", search_profile_id=role.id, **job_fields)
    job.application = Application(state=state)
    db.add(job)
    db.commit()
    return job.application


def connect(db) -> None:
    db.get(AppSettings, 1).sheet_webhook_url = CONNECTION
    db.commit()


def sent_rows(google) -> list[dict]:
    return [row for batch in google.posts for row in batch]


def test_only_a_google_apps_script_web_app_link_is_accepted():
    assert is_apps_script_link(CONNECTION)
    assert not is_apps_script_link("https://script.google.com/macros/s/AKfycb/dev")
    assert not is_apps_script_link("http://script.google.com/macros/s/AKfycb/exec")
    assert not is_apps_script_link("https://example.com/macros/s/x/exec")
    assert not is_apps_script_link(SHEET)


def test_a_row_carries_everything_the_sheet_shows(db, role, google):
    cv = CV(original_name="my_cv.pdf", stored_name="x.pdf", is_active=True)
    db.add(cv)
    db.commit()
    application = add_application(
        db, role, "011026000089", ApplicationState.APPLIED,
        location="Hyderabad", experience_min=0, experience_max=2, salary_min_lpa=3.5, salary_max_lpa=7,
        skills=["Python", "SQL"], match_score=82,
    )
    application.applied_at = utcnow()
    application.cv_id = cv.id
    application.notes = "applied. Naukri said: You have successfully applied to this job."
    sheets_sync.queue_for_sheet(db, application)
    db.commit()
    connect(db)

    result = sheets_sync.sync_pending(db)

    assert (result.sent, result.error) == (1, "")
    (row,) = sent_rows(google)
    assert row["job_id"] == "011026000089"  # text, so the leading zero survives
    assert (row["company"], row["title"], row["location"], row["role"]) == ("Acme", "AI Engineer", "Hyderabad", "AI Engineer")
    assert (row["experience"], row["salary"], row["skills"], row["match_score"]) == ("0-2 yrs", "3.5-7 LPA", "Python, SQL", 82)
    assert (row["status"], row["cv_used"]) == ("Applied", "my_cv.pdf")
    assert row["naukri_link"].endswith("job-listings-011026000089")
    assert row["applied_on"] and row["updated_on"]
    assert "successfully applied" in row["notes"]


def test_nothing_is_sent_or_lost_while_the_sheet_is_not_connected(client, db, role, onboarded, google):
    application = add_application(db, role, "1", ApplicationState.APPLIED)
    sheets_sync.queue_for_sheet(db, application)
    sheets_sync.queue_for_sheet(db, application)  # asking twice still means one row
    db.commit()

    assert sheets_sync.sync_pending(db).sent == 0
    assert google.posts == []
    assert sheets_sync.waiting_count(db) == 1
    page = client.get("/settings").text
    assert "Not connected" in page
    assert "1 application waiting." in page
    assert "Do this" in client.get("/").text  # the overview checklist still asks for the connection


def test_connecting_checks_the_link_and_sends_what_was_applied_before(client, db, role, onboarded, google):
    add_application(db, role, "applied", ApplicationState.APPLIED)
    add_application(
        db, role, "company", ApplicationState.EXTERNAL,
        apply_type=ApplyType.EXTERNAL, company_apply_url="https://careers.example.com/1",
    )
    add_application(db, role, "manual", ApplicationState.NEEDS_MANUAL)
    add_application(db, role, "skipped", ApplicationState.SKIPPED)
    add_application(db, role, "waiting", ApplicationState.QUEUED)
    add_application(db, role, "sample", ApplicationState.APPLIED, is_demo=True)

    response = client.post("/settings", data={**SETTINGS, "sheet_webhook_url": CONNECTION})

    assert response.headers["location"] == "/settings?msg=sheet_connected"
    assert google.posts[0] == []  # the connection test: an empty send
    rows = {row["job_id"]: row for row in sent_rows(google)}
    assert set(rows) == {"applied", "company", "manual"}  # no skipped, waiting or sample jobs
    assert rows["company"]["status"] == "Apply on company site"
    assert rows["company"]["apply_link"] == "https://careers.example.com/1"
    assert rows["manual"]["status"] == "Apply by hand"
    assert sheets_sync.waiting_count(db) == 0
    page = client.get("/settings").text
    assert "Every application is on your Sheet." in page
    assert "Send everything to my Sheet now" in page

    client.post("/settings", data={**SETTINGS, "sheet_webhook_url": CONNECTION})  # saving again does not resend
    assert len(google.posts) == 2


@pytest.mark.parametrize(
    "link, failure, message",
    [
        ("https://example.com/hook", None, "not the web app link of the script"),
        (CONNECTION, ValueError("not JSON"), "Who has access"),
        (CONNECTION, OSError("no route"), "could not be reached"),
    ],
)
def test_a_connection_link_that_does_not_work_is_not_saved(client, db, google, link, failure, message):
    google.failure = failure
    response = client.post("/settings", data={**SETTINGS, "sheet_webhook_url": link})
    assert response.status_code == 400
    assert message in response.text
    assert link in response.text  # what was typed is still in the box
    db.expire_all()
    assert db.get(AppSettings, 1).sheet_webhook_url == ""


def test_a_failed_send_stays_queued_and_goes_out_later(db, role, google):
    connect(db)
    application = add_application(db, role, "1", ApplicationState.APPLIED)
    sheets_sync.queue_for_sheet(db, application)
    db.commit()

    google.failure = OSError("timed out")
    result = sheets_sync.sync_pending(db)
    assert result.sent == 0
    assert "Google Sheet could not be updated" in result.error
    entry = db.scalars(select(SheetOutbox)).one()
    assert (entry.synced_at, entry.attempts) == (None, 1)
    assert "timed out" in entry.last_error

    google.failure = None
    google.answer = {"ok": False, "error": "busy, try again"}  # the script itself said no
    assert sheets_sync.sync_pending(db).sent == 0

    google.answer = {"ok": True}
    assert sheets_sync.sync_pending(db).sent == 1
    assert sheets_sync.waiting_count(db) == 0
    assert sheets_sync.sync_pending(db).sent == 0  # and not sent twice


def test_a_changed_application_is_sent_again(db, role, google):
    connect(db)
    application = add_application(db, role, "1", ApplicationState.NEEDS_MANUAL)
    sheets_sync.queue_for_sheet(db, application)
    db.commit()
    sheets_sync.sync_pending(db)

    application.state = ApplicationState.APPLIED
    sheets_sync.queue_for_sheet(db, application)
    db.commit()
    sheets_sync.sync_pending(db)

    assert [row["status"] for row in sent_rows(google)] == ["Apply by hand", "Applied"]  # the Sheet's script updates the row


def test_many_applications_go_in_batches(db, role, google):
    connect(db)
    for number in range(sheets_sync.ROWS_PER_REQUEST + 5):
        add_application(db, role, str(number), ApplicationState.APPLIED)
    assert sheets_sync.queue_everything(db) == sheets_sync.ROWS_PER_REQUEST + 5
    assert sheets_sync.sync_pending(db).sent == sheets_sync.ROWS_PER_REQUEST + 5
    assert [len(batch) for batch in google.posts] == [sheets_sync.ROWS_PER_REQUEST, 5]


def test_send_everything_button(client, db, role, google):
    add_application(db, role, "1", ApplicationState.APPLIED)
    assert client.post("/settings/sheet/sync").status_code == 400  # not connected yet

    connect(db)
    assert client.post("/settings/sheet/sync").headers["location"] == "/settings?msg=sheet_sent"
    assert [row["job_id"] for row in sent_rows(google)] == ["1"]

    google.failure = OSError("offline")
    response = client.post("/settings/sheet/sync")
    assert response.status_code == 502
    assert "Google Sheet could not be updated" in response.text


def test_settings_page_carries_the_script_to_paste(client, onboarded):
    page = client.get("/settings").text
    assert "How to connect your Sheet" in page
    assert "function doPost(e)" in page
    assert "Copy the script" in page
