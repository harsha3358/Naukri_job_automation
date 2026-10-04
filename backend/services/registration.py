"""Tells the tool's owner who is using it: name and email, nothing else.

Runs only when the owner has set a registration link, and only after the user has continued
past the welcome step that says these two details will be sent.
"""

import logging
import threading
import uuid

from sqlalchemy.orm import Session

from backend import __version__
from backend.config import config
from backend.core.clock import utcnow
from backend.core.webhook import post_json
from backend.db.database import SessionLocal
from backend.db.models import AppSettings, CandidateProfile

log = logging.getLogger(__name__)


def record_consent(db: Session) -> None:
    """The user continued past the notice. Marks their details as waiting to be sent."""
    app_settings = db.get(AppSettings, 1)
    if not app_settings.install_id:
        app_settings.install_id = uuid.uuid4().hex
    app_settings.registration_consent_at = utcnow()
    app_settings.registered_at = None  # name or email may have changed, so send again
    db.commit()


def send_pending() -> bool:
    """Send the details if the user agreed and they have not gone through yet.

    Never raises: a failed send is logged and tried again the next time the tool starts.
    """
    if not config.registration_enabled:
        return False
    with SessionLocal() as db:
        app_settings = db.get(AppSettings, 1)
        profile = db.get(CandidateProfile, 1)
        if app_settings.registration_consent_at is None or app_settings.registered_at is not None:
            return False
        if not (profile.full_name and profile.email):
            return False
        payload = {
            "name": profile.full_name,
            "email": profile.email,
            "install_id": app_settings.install_id,
            "app_version": __version__,
        }
        try:
            _post(config.registration_url, payload)
        except (OSError, ValueError) as exc:
            log.warning("Registration was not sent, will retry at next start: %s", exc)
            return False
        app_settings.registered_at = utcnow()
        db.commit()
        log.info("Registered with the tool's owner.")
        return True


def send_pending_in_background() -> None:
    """Off the request thread, so a slow or unreachable network never delays the dashboard."""
    threading.Thread(target=send_pending, name="registration", daemon=True).start()


def _post(url: str, payload: dict) -> None:
    reply = post_json(url, payload)
    if not reply.get("ok"):
        raise ValueError(f"owner's sheet refused the details: {reply.get('error', 'no reason given')}")
