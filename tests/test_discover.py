"""Search runs end to end against a stand-in for the browser, so no real page is loaded."""

import threading
from contextlib import contextmanager

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from sqlalchemy import select

from backend.config import config
from backend.db.models import Application, ApplicationState, AppSettings, CandidateProfile, Job, Run, SearchProfile
from backend.naukri import discovery, selectors
from backend.workers import discover, runner


def card(job_id: str, **overrides) -> dict:
    values = {
        "id": job_id,
        "url": f"https://www.naukri.com/job-listings-frontend-developer-0-to-2-years-{job_id}",
        "title": "Frontend Developer",
        "company": f"Company {job_id}",
        "experience": "0-2 Yrs",
        "salary": "",
        "location": "Hyderabad",
        "description": "",
        "posted": "1 day ago",
        "skills": ["React", "JavaScript"],
    }
    values.update(overrides)
    return values


class FakePage:
    """Answers like a Naukri results page. `pages` maps a part of the address to what that page shows."""

    def __init__(self, pages: dict[str, object]):
        self.pages = pages
        self.visited: list[str] = []
        self.showing: object = []
        self.url = ""

    def goto(self, url, wait_until=None):
        self.visited.append(url)
        self.url = url
        # Longest matching key wins, so "-hyderabad-2?" is preferred over "-hyderabad".
        matches = [key for key in self.pages if key in url]
        self.showing = self.pages[max(matches, key=len)] if matches else []

    def wait_for_selector(self, selector, state=None, timeout=None):
        if self.showing == "blocked":
            raise PlaywrightTimeout("timeout")

    def query_selector(self, selector):
        return object() if self.showing in ("no results", "fallback") else None

    def eval_on_selector_all(self, selector, script, arg=None):
        return self.showing

    def wait_for_timeout(self, ms):
        pass

    def screenshot(self, path, full_page=False):
        with open(path, "wb") as file:
            file.write(b"png")

    def content(self):
        return "<h1>Access Denied</h1>"


@pytest.fixture
def browser(monkeypatch):
    """Call with the pages to serve; returns the fake page so the test can see what was visited."""

    def install(pages: dict[str, object]) -> FakePage:
        page = FakePage(pages)

        class Context:
            pages = [page]

        @contextmanager
        def fake_open_browser():
            yield Context()

        monkeypatch.setattr(discover, "open_browser", fake_open_browser)
        return page

    return install


@pytest.fixture
def role(db) -> SearchProfile:
    profile = db.get(CandidateProfile, 1)
    profile.experience_years = 0.0
    profile.skills = ["React", "JavaScript"]
    role = SearchProfile(role="Frontend Developer", locations=["Hyderabad"])
    db.add(role)
    db.commit()
    return role


def last_run(db) -> Run:
    db.expire_all()
    return db.scalars(select(Run).order_by(Run.id.desc())).first()


def test_search_stores_scores_and_queues_what_it_finds(db, role, browser):
    page = browser({"hyderabad": [card("1"), card("2", title="Accountant", skills=["Tally"]), card("3", location="Pune")]})

    discover.run_discovery()

    assert page.visited == [
        "https://www.naukri.com/frontend-developer-jobs-in-hyderabad?k=frontend%20developer&l=hyderabad&experience=0&jobAge=7"
    ]
    states = dict(db.execute(select(Job.naukri_job_id, Application.state).join(Application)).all())
    assert states == {"1": ApplicationState.QUEUED, "2": ApplicationState.SKIPPED, "3": ApplicationState.SKIPPED}
    run = last_run(db)
    assert (run.found, run.matched, run.skipped, run.error) == (3, 1, 2, "")
    assert run.finished_at is not None


def test_searching_again_adds_nothing_new(db, role, browser):
    browser({"hyderabad": [card("1"), card("2")]})
    discover.run_discovery()
    discover.run_discovery()

    assert len(db.scalars(select(Job)).all()) == 2
    run = last_run(db)
    assert (run.found, run.matched, run.skipped) == (2, 0, 0)


def test_each_city_is_searched_and_a_full_page_leads_to_the_next(db, role, browser, monkeypatch):
    monkeypatch.setattr(discovery, "MAX_PAGES_PER_SEARCH", 2)
    role.locations = ["Hyderabad", "Pune"]
    db.commit()
    full_page = [card(str(number)) for number in range(selectors.RESULTS_PER_PAGE)]
    page = browser({"in-hyderabad?": full_page, "in-hyderabad-2?": [card("900")], "in-pune?": [card("901", location="Pune")]})

    discover.run_discovery()

    assert [url.split("?")[0].rsplit("/", 1)[1] for url in page.visited] == [
        "frontend-developer-jobs-in-hyderabad",
        "frontend-developer-jobs-in-hyderabad-2",
        "frontend-developer-jobs-in-pune",
    ]
    assert last_run(db).found == selectors.RESULTS_PER_PAGE + 2


def test_never_reads_more_pages_than_the_limit(db, role, browser):
    full_page = [card(str(number)) for number in range(selectors.RESULTS_PER_PAGE)]
    page = browser({"hyderabad": full_page})
    discover.run_discovery()
    assert len(page.visited) == discovery.MAX_PAGES_PER_SEARCH == 1


def test_a_repeated_page_is_not_counted_twice(db, role, browser, monkeypatch):
    # What happened on the first real search: "page 2" came back with page 1's jobs again.
    monkeypatch.setattr(discovery, "MAX_PAGES_PER_SEARCH", 3)
    full_page = [card(str(number)) for number in range(selectors.RESULTS_PER_PAGE)]
    page = browser({"hyderabad": full_page})

    discover.run_discovery()

    assert len(page.visited) == 2  # stopped as soon as a page repeated
    assert last_run(db).found == selectors.RESULTS_PER_PAGE


@pytest.mark.parametrize("showing", ["no results", "fallback"])
def test_suggested_jobs_on_a_no_result_page_are_not_taken_as_results(client, db, role, onboarded, browser, showing):
    page = browser({"hyderabad": showing})
    discover.run_discovery()
    assert len(page.visited) == 1  # no second page is asked for after "no result"
    assert db.scalars(select(Job)).first() is None
    run = last_run(db)
    assert (run.found, run.failed, run.error) == (0, 1, "")
    assert 'Naukri answered "No result found" to 1 of the searches' in client.get("/jobs").text.replace("&#34;", '"')


def test_a_page_the_tool_does_not_understand_stops_the_run_and_keeps_evidence(db, role, browser):
    second = SearchProfile(role="React Developer", locations=["Hyderabad"])
    db.add(second)
    db.commit()
    page = browser({"frontend": "blocked", "react": [card("1")]})

    discover.run_discovery()

    assert len(page.visited) == 1  # the second role was not searched after the first failed
    assert db.scalars(select(Job)).first() is None
    run = last_run(db)
    assert "Naukri did not show a list of jobs" in run.error
    assert run.finished_at is not None
    saved = sorted(path.suffix for path in (config.data_dir / "screenshots").iterdir())
    assert ".html" in saved and ".png" in saved


def test_search_with_no_role_switched_on_explains_itself(db, browser):
    page = browser({})
    discover.run_discovery()
    assert page.visited == []
    assert "No role is switched on" in last_run(db).error


def test_an_unexpected_crash_still_ends_the_run_with_a_reason(db, role, browser, monkeypatch):
    browser({"hyderabad": [card("1")]})

    def explode(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(discover, "ingest_jobs", explode)
    discover.run_discovery()
    run = last_run(db)
    assert "Something unexpected went wrong" in run.error
    assert run.finished_at is not None


# --- one browser task at a time ------------------------------------------------


def test_runner_refuses_a_second_task_and_frees_itself_after_a_crash():
    release = threading.Event()
    done = threading.Event()

    def slow():
        release.wait(5)

    def crash():
        try:
            raise RuntimeError("boom")
        finally:
            done.set()

    assert runner.start("first", slow) is True
    assert runner.current() == "first"
    assert runner.start("second", slow) is False
    release.set()
    _wait_until_idle()

    assert runner.start("crashing", crash) is True
    done.wait(5)
    _wait_until_idle()
    assert runner.current() == ""


def _wait_until_idle() -> None:
    for _ in range(200):
        if runner.current() == "" and runner.start("probe", lambda: None):
            break
        threading.Event().wait(0.01)
    for _ in range(200):
        if runner.current() == "":
            return
        threading.Event().wait(0.01)
    raise AssertionError("runner never became idle")


def test_search_button_starts_a_search_and_shows_progress(client, db, role, onboarded, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def fake_search():
        started.set()
        release.wait(5)

    monkeypatch.setattr("backend.api.naukri.run_discovery", fake_search)
    try:
        assert client.post("/naukri/search").headers["location"] == "/jobs"
        started.wait(5)
        page = client.get("/jobs").text
        assert "Searching Naukri" in page
        assert 'http-equiv="refresh"' in page
        assert client.post("/naukri/search").headers["location"] == "/jobs?msg=busy"
        assert client.post("/naukri/connect").headers["location"] == "/settings?msg=busy"
    finally:
        release.set()
        _wait_until_idle()
    assert "Search Naukri now" in client.get("/jobs").text


def test_jobs_page_reports_the_last_search(client, db, role, onboarded, browser):
    browser({"hyderabad": [card("1"), card("2", location="Pune")]})
    discover.run_discovery()
    page = client.get("/jobs").text
    assert "Naukri listed 2 jobs, 2 of them new to the tool." in page

    browser({"hyderabad": "blocked"})
    discover.run_discovery()
    assert "did not finish" in client.get("/jobs").text


def test_connect_records_whether_the_user_logged_in(db, monkeypatch):
    from backend.workers import connect

    monkeypatch.setattr(connect, "wait_for_user_login", lambda: True)
    connect.run_connect()
    db.expire_all()
    assert db.get(AppSettings, 1).naukri_connected_at is not None

    monkeypatch.setattr(connect, "wait_for_user_login", lambda: False)
    connect.run_connect()
    db.expire_all()
    assert db.get(AppSettings, 1).naukri_connected_at is None
