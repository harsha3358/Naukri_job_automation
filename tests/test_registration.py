import pytest

from backend import __version__
from backend.config import config
from backend.db.models import AppSettings
from backend.services import registration

OWNER_LINK = "https://script.google.com/macros/s/AKfycbTESTONLY/exec"
WELCOME = {"full_name": "Ravi Kumar", "email": "ravi@example.com", "experience_years": "0"}


@pytest.fixture
def sent(monkeypatch):
    """Captures what would be posted to the owner, and sends in the same thread so tests can see it."""
    posts: list[tuple[str, dict]] = []
    monkeypatch.setattr(registration, "_post", lambda url, payload: posts.append((url, payload)))
    monkeypatch.setattr(registration, "send_pending_in_background", registration.send_pending)
    return posts


@pytest.fixture
def registration_on(monkeypatch):
    monkeypatch.setattr(config, "registration_url", OWNER_LINK)


def test_nothing_is_collected_until_the_owner_sets_a_link(client, db, sent):
    assert "sent to the maker" not in client.get("/welcome").text
    assert client.post("/welcome", data=WELCOME).status_code == 303
    assert sent == []
    assert db.get(AppSettings, 1).registration_consent_at is None


def test_a_link_that_is_not_an_apps_script_https_link_counts_as_off(client, monkeypatch, sent):
    monkeypatch.setattr(config, "registration_url", "http://example.com/collect")
    assert "sent to the maker" not in client.get("/welcome").text
    client.post("/welcome", data=WELCOME)
    assert sent == []


def test_welcome_shows_the_notice_and_sends_only_name_and_email(client, db, sent, registration_on):
    page = client.get("/welcome").text
    assert "<strong>name and email</strong> are sent to the maker of this tool" in page

    assert client.post("/welcome", data=WELCOME).status_code == 303

    (url, payload), = sent
    assert url == OWNER_LINK
    assert set(payload) == {"name", "email", "install_id", "app_version"}
    assert (payload["name"], payload["email"], payload["app_version"]) == ("Ravi Kumar", "ravi@example.com", __version__)
    assert len(payload["install_id"]) == 32

    db.expire_all()
    assert db.get(AppSettings, 1).registered_at is not None


def test_email_is_required_when_registration_is_on(client, sent, registration_on):
    response = client.post("/welcome", data={"full_name": "Ravi Kumar"})
    assert response.status_code == 400
    assert "Please type your email, or use Skip setup." in response.text
    assert sent == []


def test_skipping_setup_sends_nothing(client, db, sent, registration_on):
    client.post("/welcome/finish")
    assert registration.send_pending() is False
    assert sent == []


def test_a_failed_send_is_retried_later(client, db, monkeypatch, registration_on):
    monkeypatch.setattr(registration, "send_pending_in_background", registration.send_pending)

    def offline(url, payload):
        raise OSError("no internet")

    monkeypatch.setattr(registration, "_post", offline)
    assert client.post("/welcome", data=WELCOME).status_code == 303  # setup is not held up
    db.expire_all()
    assert db.get(AppSettings, 1).registered_at is None

    posts = []
    monkeypatch.setattr(registration, "_post", lambda url, payload: posts.append(payload))
    assert registration.send_pending() is True  # what the next start of the tool does
    assert len(posts) == 1
    assert registration.send_pending() is False  # and it is not sent twice


def test_running_setup_again_keeps_the_same_install_id(client, db, sent, registration_on):
    client.post("/welcome", data=WELCOME)
    client.post("/welcome", data={**WELCOME, "email": "ravi.new@example.com"})
    first, second = (payload for _, payload in sent)
    assert first["install_id"] == second["install_id"]
    assert second["email"] == "ravi.new@example.com"


def test_owner_refusal_counts_as_a_failure(monkeypatch):
    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"ok": false, "error": "missing or invalid details"}'

    monkeypatch.setattr("backend.core.webhook.urllib.request.urlopen", lambda request, timeout: Reply())
    with pytest.raises(ValueError, match="missing or invalid details"):
        registration._post(OWNER_LINK, {"name": "x"})
