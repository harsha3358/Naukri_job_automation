import logging

from backend.core.clock import utcnow
from backend.db.database import SessionLocal
from backend.db.models import AppSettings
from backend.naukri.browser import BrowserUnavailable
from backend.naukri.session import wait_for_user_login

log = logging.getLogger(__name__)


def run_connect() -> None:
    """Let the user log in to Naukri in the tool's browser window, and remember whether they did."""
    try:
        logged_in = wait_for_user_login()
    except BrowserUnavailable as exc:
        log.warning("Connect could not start: %s", exc)
        logged_in = False
    with SessionLocal() as db:
        db.get(AppSettings, 1).naukri_connected_at = utcnow() if logged_in else None
        db.commit()
    log.info("Naukri connect finished: logged_in=%s", logged_in)
