import logging
import time
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from backend.naukri import selectors
from backend.naukri.browser import open_browser

log = logging.getLogger(__name__)

LOGIN_WAIT_SECONDS = 300
# Logged out, Naukri first shows the account address and only a moment later sends the browser
# to its login page. Trusting the address straight away reported "connected" with nobody logged
# in (2026-10-04). It only counts once it has stayed put this long.
SETTLE_SECONDS = 6


def is_logged_in(page: Page) -> bool:
    """Open the account home page and see whether Naukri lets the browser stay there."""
    page.goto(selectors.ACCOUNT_HOME_URL, wait_until="domcontentloaded")
    return _stays_on_account_page(page)


def wait_for_user_login() -> bool:
    """Open Naukri's login page in a visible window and wait for the user to log in themselves.

    The tool never types or stores the password. Returns True once Naukri keeps the browser on
    the account home page, False if the window is closed or the wait runs out.
    """
    with open_browser() as context:
        page = context.pages[0] if context.pages else context.new_page()
        try:
            if is_logged_in(page):  # still logged in from an earlier time
                return True
            deadline = time.monotonic() + LOGIN_WAIT_SECONDS
            while time.monotonic() < deadline:
                # After a successful login Naukri sends the browser back to the account home page.
                if _on_account_page(page) and _stays_on_account_page(page):
                    return True
                page.wait_for_timeout(1000)
        except PlaywrightError as exc:
            log.info("Login window ended early: %s", exc.message.splitlines()[0])
        return False


def _on_account_page(page: Page) -> bool:
    return urlsplit(page.url).path.startswith(selectors.ACCOUNT_PATH_PREFIX)


def _stays_on_account_page(page: Page) -> bool:
    for _ in range(SETTLE_SECONDS):
        page.wait_for_timeout(1000)
        if not _on_account_page(page):
            return False
    return True
