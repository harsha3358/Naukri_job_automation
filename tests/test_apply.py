"""The apply run, in practice and real mode, against a stand-in for the logged-in browser."""

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from sqlalchemy import select, text

from backend.config import config
from backend.core.clock import to_local, utcnow
from backend.db.database import add_missing_columns, engine
from backend.db.models import (
    CV,
    Application,
    ApplicationState,
    ApplyMode,
    AppSettings,
    ApplyType,
    Job,
    Run,
    SearchProfile,
)
from backend.naukri import selectors
from backend.naukri.apply import click_apply
from backend.workers import apply as apply_worker

COMPANY_LINK = "https://careers.example.com/job/1"
SUCCESS = "You have successfully applied to this job."


class FakeResponse:
    def __init__(self, url: str, body: dict):
        self.url = url
        self.ok = True
        self._body = body

    def json(self):
        return self._body


class FakeJobPage:
    """`jobs` maps a job link to how its page behaves:

    "direct"          job data says normal apply, Apply button shown
    "company"         job data carries the company's link, company-site button shown
    <a link>          as "company", with that link
    "already applied" job data carries the date it was applied to
    "logged out"      job data says nobody is logged in
    "stale button"    job data says company site, but the page still shows the plain Apply button
    "no button"       job data arrives, the expected button never does
    "none"            no job data at all (job gone, or Naukri refusing)

    `outcomes` maps a job link to what a click on Apply leads to: "ok" (the default),
    "questions" (Naukri does not confirm), "silent" (no answer), "quota" (ok, and Naukri's
    daily limit is now reached). Every click is recorded in `clicks`.
    """

    def __init__(self, jobs: dict[str, str], outcomes: dict[str, str] | None = None):
        self.jobs = jobs
        self.outcomes = outcomes or {}
        self.visited: list[str] = []
        self.clicks: list[str] = []
        self.showing = "none"
        self.url = ""
        self._waiting_for = None

    @contextmanager
    def expect_response(self, predicate, timeout=None):
        answer = SimpleNamespace(value=None)
        self._waiting_for = (predicate, answer)
        yield answer
        self._waiting_for = None
        if answer.value is None:
            raise PlaywrightTimeout("no answer")

    def _deliver(self, *responses: FakeResponse) -> None:
        predicate, answer = self._waiting_for
        for response in responses:
            if answer.value is None and predicate(response):
                answer.value = response

    def goto(self, url, wait_until=None):
        self.visited.append(url)
        self.url = url
        self.showing = self.jobs.get(url, "none")
        if self.showing == "none":
            return
        details = {}
        if self.showing in ("company", "stale button") or self.showing.startswith(("http", "javascript")):
            details["applyRedirectUrl"] = COMPANY_LINK if self.showing in ("company", "stale button") else self.showing
        if self.showing == "already applied":
            details["applyDate"] = "2026-10-03 10:00:00"
        self._deliver(
            FakeResponse("https://www.naukri.com/jobapi/v2/search/simjobs/1", {"jobDetails": {"applyRedirectUrl": "https://wrong.example"}}),
            FakeResponse("https://www.naukri.com/jobapi/v4/job/1?microsite=y", {"loggedIn": self.showing != "logged out", "jobDetails": details}),
        )

    def click(self, selector):
        assert selector == selectors.APPLY_BUTTON, "the tool may only ever click Naukri's Apply button"
        self.clicks.append(self.url)
        outcome = self.outcomes.get(self.url, "ok")
        if outcome == "silent":
            return
        job_id = self.url.split("job-listings-")[1]
        if outcome == "questions":
            body = {"applyStatus": {job_id: 400}, "jobs": [{"jobId": job_id, "status": 400, "message": "Please answer the recruiter's questions."}]}
        else:
            applied_today = 50 if outcome == "quota" else len(self.clicks)
            body = {
                "applyStatus": {job_id: 200},
                "jobs": [{"jobId": job_id, "status": 200, "message": SUCCESS}],
                "quotaDetails": {"dailyApplied": applied_today, "dailyQuota": 50},
            }
        self._deliver(FakeResponse("https://www.naukri.com/cloudgateway-workflow/workflow-services/apply-workflow/v1/apply", body))

    def _buttons(self) -> set[str]:
        if self.showing in ("direct", "stale button"):
            return {selectors.APPLY_BUTTON}
        if self.showing in ("no button", "none", "logged out", "already applied"):
            return set()
        return {selectors.COMPANY_SITE_BUTTON}

    def wait_for_selector(self, selector, state=None, timeout=None):
        if selector not in self._buttons():
            raise PlaywrightTimeout("timeout")

    def query_selector(self, selector):
        return object() if selector in self._buttons() else None

    def wait_for_timeout(self, ms):
        pass

    def screenshot(self, path, full_page=False):
        with open(path, "wb") as file:
            file.write(b"png")

    def content(self):
        return "<html></html>"


@pytest.fixture
def role(db) -> SearchProfile:
    role = SearchProfile(role="AI Engineer", locations=["Hyderabad"])
    db.add(role)
    db.commit()
    return role


def add_job(db, role, job_id: str, score: int = 80, state: str = ApplicationState.QUEUED, **overrides) -> str:
    url = f"https://www.naukri.com/job-listings-{job_id}"
    # The title matches the role, so the job still qualifies when a settings change re-checks it.
    job = Job(naukri_job_id=job_id, title="AI Engineer", url=url, match_score=score, search_profile_id=role.id, **overrides)
    job.application = Application(state=state)
    db.add(job)
    db.commit()
    return url


@pytest.fixture
def browser(monkeypatch):
    def install(jobs: dict[str, str], logged_in: bool = True, outcomes: dict[str, str] | None = None) -> FakeJobPage:
        page = FakeJobPage(jobs, outcomes)

        class Context:
            pages = [page]

        @contextmanager
        def fake_open_browser():
            yield Context()

        monkeypatch.setattr(apply_worker, "open_browser", fake_open_browser)
        monkeypatch.setattr(apply_worker, "is_logged_in", lambda _page: logged_in)
        return page

    return install


@pytest.fixture
def real_mode(db):
    db.get(AppSettings, 1).apply_mode = ApplyMode.REAL
    db.commit()


def job_row(db, job_id: str) -> Job:
    db.expire_all()
    return db.scalars(select(Job).where(Job.naukri_job_id == job_id)).one()


def last_run(db) -> Run:
    db.expire_all()
    return db.scalars(select(Run).order_by(Run.id.desc())).first()


# --- practice mode -------------------------------------------------------------


def test_practice_run_reads_each_waiting_job_and_clicks_nothing(db, role, browser):
    direct = add_job(db, role, "direct", score=90)
    company = add_job(db, role, "company", score=70)
    page = browser({direct: "direct", company: "company"})

    apply_worker.run_apply()

    assert page.visited == [direct, company]  # best match first
    assert page.clicks == []
    job = job_row(db, "direct")
    assert (job.application.state, job.apply_type, job.application.applied_at) == (ApplicationState.QUEUED, ApplyType.DIRECT, None)
    assert "It was not clicked" in job.application.notes

    job = job_row(db, "company")
    assert (job.application.state, job.apply_type, job.company_apply_url) == (ApplicationState.EXTERNAL, ApplyType.EXTERNAL, COMPANY_LINK)

    run = last_run(db)
    assert (run.kind, run.found, run.applied, run.matched, run.skipped, run.failed, run.error) == ("apply", 2, 0, 1, 1, 0, "")


def test_practice_is_the_mode_a_new_setup_starts_in(db):
    assert db.get(AppSettings, 1).apply_mode == ApplyMode.DRY_RUN


# --- reading the job page ------------------------------------------------------


def test_the_first_apply_button_naukri_paints_is_not_trusted(db, role, browser, real_mode):
    # Seen live: a company-site job shows the plain Apply button until its data has loaded.
    url = add_job(db, role, "optum")
    page = browser({url: "stale button"})
    apply_worker.run_apply()
    job = job_row(db, "optum")
    assert page.clicks == []
    assert job.apply_type == ApplyType.UNKNOWN  # not read as a normal apply job
    assert job.application.state == ApplicationState.QUEUED
    assert "no Apply button was found" in job.application.notes


def test_a_company_link_that_is_not_a_web_address_is_not_kept(db, role, browser):
    url = add_job(db, role, "odd")
    browser({url: "javascript:alert(1)"})
    apply_worker.run_apply()
    job = job_row(db, "odd")
    assert (job.application.state, job.company_apply_url) == (ApplicationState.EXTERNAL, "")


def test_a_job_already_applied_to_is_recorded_and_not_applied_to_again(db, role, browser, real_mode):
    url = add_job(db, role, "old")
    page = browser({url: "already applied"})
    apply_worker.run_apply()
    job = job_row(db, "old")
    assert page.clicks == []
    assert job.application.state == ApplicationState.APPLIED
    assert to_local(job.application.applied_at).replace(tzinfo=None) == datetime(2026, 10, 3, 10, 0, 0)
    assert "already applied" in job.application.notes


# --- stopping safely -----------------------------------------------------------


def test_nothing_is_opened_when_naukri_is_not_logged_in(db, role, browser, real_mode):
    db.get(AppSettings, 1).naukri_connected_at = utcnow()
    add_job(db, role, "a")
    page = browser({}, logged_in=False)

    apply_worker.run_apply()

    assert (page.visited, page.clicks) == ([], [])
    assert "Naukri is not logged in" in last_run(db).error
    assert db.get(AppSettings, 1).naukri_connected_at is None  # the dashboard stops saying "Connected"


def test_being_logged_out_in_the_middle_stops_the_run(db, role, browser, real_mode):
    db.get(AppSettings, 1).naukri_connected_at = utcnow()
    first = add_job(db, role, "a", score=90)
    second = add_job(db, role, "b", score=80)
    third = add_job(db, role, "c", score=70)
    page = browser({first: "direct", second: "logged out", third: "direct"})

    apply_worker.run_apply()

    assert page.visited == [first, second]
    assert page.clicks == [first]
    assert "Naukri logged the tool out" in last_run(db).error
    assert db.get(AppSettings, 1).naukri_connected_at is None
    assert job_row(db, "b").application.state == ApplicationState.QUEUED  # nothing was concluded about it


def test_only_real_waiting_jobs_of_switched_on_roles_are_opened(db, role, browser, real_mode):
    off_role = SearchProfile(role="Old role", is_active=False)
    db.add(off_role)
    db.commit()
    waiting = add_job(db, role, "waiting")
    add_job(db, role, "sample", is_demo=True)
    add_job(db, role, "skipped", state=ApplicationState.SKIPPED)
    add_job(db, role, "applied", state=ApplicationState.APPLIED)
    add_job(db, role, "manual", state=ApplicationState.NEEDS_MANUAL)
    add_job(db, off_role, "role-off")
    page = browser({waiting: "direct"})

    apply_worker.run_apply()

    assert page.visited == [waiting]
    assert page.clicks == [waiting]


def test_three_problems_in_a_row_stop_the_run_and_keep_pictures(db, role, browser):
    urls = [add_job(db, role, name, score=score) for name, score in (("a", 90), ("b", 80), ("c", 70), ("d", 60))]
    page = browser({urls[0]: "none", urls[1]: "no button", urls[2]: "none"})  # nothing readable anywhere

    apply_worker.run_apply()

    assert page.visited == urls[:3]
    run = last_run(db)
    assert run.failed == 3
    assert "3 jobs in a row could not be read or applied to" in run.error
    assert "no Apply button was found" in job_row(db, "a").application.notes
    assert job_row(db, "a").application.state == ApplicationState.QUEUED
    assert len(list((config.data_dir / "screenshots").glob("job-*.png"))) >= 1


# --- real mode -----------------------------------------------------------------


def test_real_mode_applies_and_records_what_naukri_said(db, role, browser, real_mode):
    db.add(CV(original_name="cv.pdf", stored_name="x.pdf", is_active=True))
    db.commit()
    direct = add_job(db, role, "direct", score=90)
    company = add_job(db, role, "company", score=70)
    page = browser({direct: "direct", company: "company"})

    apply_worker.run_apply()

    assert page.clicks == [direct]  # one click, on the job with Naukri's Apply button only
    job = job_row(db, "direct")
    assert job.application.state == ApplicationState.APPLIED
    assert job.application.applied_at is not None
    assert job.application.cv_id == db.scalars(select(CV.id)).one()
    assert job.application.attempts == 1
    assert SUCCESS in job.application.notes
    assert job_row(db, "company").application.state == ApplicationState.EXTERNAL

    run = last_run(db)
    assert (run.found, run.applied, run.skipped, run.failed, run.error) == (2, 1, 1, 0, "")


@pytest.mark.parametrize("outcome, expected_note", [("questions", "Please answer the recruiter's questions."), ("silent", "Naukri gave no answer")])
def test_an_unconfirmed_application_is_handed_to_the_user_and_never_retried(db, role, browser, real_mode, outcome, expected_note):
    url = add_job(db, role, "hard")
    page = browser({url: "direct"}, outcomes={url: outcome})

    apply_worker.run_apply()

    job = job_row(db, "hard")
    assert job.application.state == ApplicationState.NEEDS_MANUAL
    assert job.application.applied_at is None
    assert expected_note in job.application.notes
    assert "check it yourself" in job.application.notes
    assert last_run(db).failed == 1
    assert len(list((config.data_dir / "screenshots").glob("apply-*.png"))) >= 1

    apply_worker.run_apply()  # a later run leaves it alone: the first click may have gone through
    assert page.clicks == [url]


def test_the_daily_limit_is_respected_across_runs(db, role, browser, real_mode):
    db.get(AppSettings, 1).daily_apply_cap = 2
    db.commit()
    urls = [add_job(db, role, name, score=score) for name, score in (("a", 90), ("b", 80), ("c", 70))]
    page = browser({url: "direct" for url in urls})

    apply_worker.run_apply()
    assert page.clicks == urls[:2]

    apply_worker.run_apply()
    assert page.clicks == urls[:2]  # nothing more today
    assert "today's limit is used up" in last_run(db).error
    assert job_row(db, "c").application.state == ApplicationState.QUEUED


def test_the_run_stops_when_naukri_says_its_own_daily_limit_is_reached(db, role, browser, real_mode):
    first = add_job(db, role, "a", score=90)
    second = add_job(db, role, "b", score=80)
    page = browser({first: "direct", second: "direct"}, outcomes={first: "quota"})

    apply_worker.run_apply()

    assert page.clicks == [first]
    assert job_row(db, "a").application.state == ApplicationState.APPLIED
    assert "Naukri's own limit" in last_run(db).error


def test_an_answer_about_a_different_job_does_not_count_as_applied():
    class Page(FakeJobPage):
        def click(self, selector):
            self._deliver(FakeResponse(
                "https://www.naukri.com/x/apply-workflow/v1/apply",
                {"applyStatus": {"other": 200}, "jobs": [{"jobId": "other", "status": 200, "message": SUCCESS}]},
            ))

    assert click_apply(Page({}), "mine").applied is False


# --- dashboard -----------------------------------------------------------------


def test_jobs_page_offers_the_run_for_the_chosen_mode(client, db, role, onboarded, browser):
    direct = add_job(db, role, "direct", score=90)
    company = add_job(db, role, "company", score=70)

    assert "Connect Naukri on the Settings page" in client.get("/jobs").text  # not connected yet

    db.get(AppSettings, 1).naukri_connected_at = utcnow()
    db.commit()
    assert "Practice run on 2 waiting jobs" in client.get("/jobs").text

    browser({direct: "direct", company: "company"})
    apply_worker.run_apply()
    page = client.get("/jobs").text.replace("&#39;", "'")
    assert f'<a href="{COMPANY_LINK}" target="_blank" rel="noopener">Apply on company site</a>' in page
    assert "Practice run on 1 waiting job<" in page
    assert "Opened 2 jobs: 0 applied, 1 ready to apply (practice), 1 applied to on the company's site, 0 with a problem." in page

    settings = {"daily_apply_cap": "20", "min_match_score": "60"}
    assert client.post("/settings", data={**settings, "apply_mode": "sideways"}).status_code == 400
    client.post("/settings", data={**settings, "apply_mode": "real"})
    page = client.get("/jobs").text
    assert "Apply to waiting jobs now" in page
    assert "This sends real applications" in page
    assert "1 waiting, 20 left in today" in page

    client.post("/settings", data=settings)  # a form without the choice leaves the mode alone
    db.expire_all()
    assert db.get(AppSettings, 1).apply_mode == ApplyMode.REAL


# --- database upgrade ----------------------------------------------------------


def test_an_older_database_gets_the_new_columns_without_losing_data(db, role):
    add_job(db, role, "kept", score=77)
    db.get(AppSettings, 1).daily_apply_cap = 7
    db.commit()
    db.close()
    with engine.begin() as connection:  # make the database look like one from before these columns existed
        connection.execute(text("ALTER TABLE jobs DROP COLUMN company_apply_url"))
        connection.execute(text("ALTER TABLE settings DROP COLUMN apply_mode"))

    backups_before = set(config.data_dir.glob("data-before-upgrade-*.db"))
    assert sorted(add_missing_columns()) == ["jobs.company_apply_url", "settings.apply_mode"]
    assert add_missing_columns() == []  # running it again changes nothing
    assert len(set(config.data_dir.glob("data-before-upgrade-*.db")) - backups_before) == 1  # a copy was kept first

    job = job_row(db, "kept")
    assert (job.match_score, job.company_apply_url) == (77, "")
    app_settings = db.get(AppSettings, 1)
    assert (app_settings.daily_apply_cap, app_settings.apply_mode) == (7, ApplyMode.DRY_RUN)
