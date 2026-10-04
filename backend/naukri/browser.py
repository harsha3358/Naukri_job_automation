import logging
from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import BrowserContext, Playwright, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from backend.config import config

log = logging.getLogger(__name__)

# Browsers already on a Windows PC, in the order tried. Using one of these means the user
# does not have to download a separate browser.
CHANNELS = ("msedge", "chrome")


class BrowserUnavailable(Exception):
    """No usable browser could be started. The message is safe to show to the user."""


@contextmanager
def open_browser() -> Iterator[BrowserContext]:
    """A visible browser window with the tool's own saved profile, so a Naukri login survives between runs.

    Always visible, never headless. Naukri refuses an invisible browser ("Access Denied") and
    then keeps treating that profile as suspect: later searches from it come back as "no result"
    padded with unrelated jobs. Seen on 2026-10-04. Do not add a headless option.

    The profile folder can be used by one browser at a time; callers go through
    `backend.workers.runner`, which allows a single browser task at once.
    """
    profile = config.data_dir / "browser_profile"
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = _launch(playwright, str(profile))
        try:
            yield context
        finally:
            try:
                context.close()
            except PlaywrightError:
                pass  # the user already closed the window


def _launch(playwright: Playwright, profile: str) -> BrowserContext:
    problems: list[str] = []
    for channel in CHANNELS:
        try:
            # no_viewport lets the window use its real size instead of a fixed one.
            # chromium_sandbox: Playwright switches the browser's own sandbox off by default
            # ("--no-sandbox", which Edge warns about in a banner). The user logs in to their
            # account in this window, so it runs with the sandbox on, like a normal browser.
            return playwright.chromium.launch_persistent_context(
                profile, channel=channel, headless=False, no_viewport=True, chromium_sandbox=True
            )
        except PlaywrightError as exc:
            problems.append(f"{channel}: {exc.message.splitlines()[0]}")
    log.warning("Could not start a browser: %s", " | ".join(problems))
    raise BrowserUnavailable(
        "Could not open Microsoft Edge or Google Chrome. Close any browser window the tool opened earlier, "
        "make sure Edge or Chrome is installed, and try again."
    )
