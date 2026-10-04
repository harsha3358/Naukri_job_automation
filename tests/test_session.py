"""Login detection, against a stand-in page whose address changes over time like Naukri's does."""

from contextlib import contextmanager

import pytest
from playwright.sync_api import Error as PlaywrightError

from backend.naukri import session

HOME = "https://www.naukri.com/mnjuser/homepage"
LOGIN = "https://www.naukri.com/nlogin/login?URL=https://www.naukri.com/mnjuser/homepage"


class FakePage:
    """`script` maps a second on the clock to the address the browser moves to at that second."""

    def __init__(self, script: dict[int, str], closes_at: int | None = None):
        self.script = script
        self.closes_at = closes_at
        self.clock = 0
        self.url = ""

    def goto(self, url, wait_until=None):
        self.url = url

    def wait_for_timeout(self, ms):
        self.clock += ms // 1000
        if self.closes_at is not None and self.clock >= self.closes_at:
            raise PlaywrightError("Target page, context or browser has been closed")
        for second in sorted(self.script):
            if second <= self.clock:
                self.url = self.script[second]


@pytest.fixture
def window(monkeypatch):
    def install(page: FakePage) -> FakePage:
        class Context:
            pages = [page]

        @contextmanager
        def fake_open_browser():
            yield Context()

        monkeypatch.setattr(session, "open_browser", fake_open_browser)
        monkeypatch.setattr(session.time, "monotonic", lambda: page.clock)
        return page

    return install


def test_the_moment_before_naukri_redirects_to_login_is_not_taken_as_logged_in(window):
    # What really happened: the address is the account page for an instant, then the login page.
    page = window(FakePage({2: LOGIN}))
    assert session.wait_for_user_login() is False
    assert page.clock >= session.LOGIN_WAIT_SECONDS  # it kept waiting for the user the whole time


def test_logging_in_is_detected_once_the_account_page_stays(window):
    page = window(FakePage({2: LOGIN, 40: HOME}))
    assert session.wait_for_user_login() is True
    assert 40 + session.SETTLE_SECONDS <= page.clock < 60


def test_already_logged_in_is_recognised_without_waiting_for_a_login(window):
    page = window(FakePage({}))
    assert session.wait_for_user_login() is True
    assert page.clock == session.SETTLE_SECONDS


def test_a_login_that_bounces_back_to_the_login_page_does_not_count(window):
    # e.g. wrong OTP: Naukri shows the account address briefly, then the login page again
    window(FakePage({2: LOGIN, 30: HOME, 32: LOGIN}))
    assert session.wait_for_user_login() is False


def test_closing_the_window_means_not_logged_in(window):
    window(FakePage({2: LOGIN}, closes_at=20))
    assert session.wait_for_user_login() is False
