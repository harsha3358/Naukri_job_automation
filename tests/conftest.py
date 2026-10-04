import atexit
import os
import shutil
import tempfile

# Point the app at throwaway folders before anything imports backend.config.
_TEST_ROOT = tempfile.mkdtemp(prefix="nja-test-")
os.environ["NJA_DATA_DIR"] = os.path.join(_TEST_ROOT, "data")
os.environ["NJA_RESUMES_DIR"] = os.path.join(_TEST_ROOT, "resumes")
# Environment variables win over a developer's .env, so tests never pick up a real owner link.
os.environ["NJA_REGISTRATION_URL"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.config import config  # noqa: E402
from backend.db.database import SessionLocal, engine, init_db  # noqa: E402
from backend.db.models import AppSettings, Base  # noqa: E402
from backend.main import app  # noqa: E402


@atexit.register
def _cleanup() -> None:
    engine.dispose()
    shutil.rmtree(_TEST_ROOT, ignore_errors=True)


@pytest.fixture
def db():
    """A fresh, empty database and resumes folder for each test."""
    init_db()
    Base.metadata.drop_all(engine)
    init_db()
    for leftover in config.resumes_dir.iterdir():
        leftover.unlink()
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client(db):
    # Host must be one the app trusts; redirects are asserted by hand.
    with TestClient(app, base_url="http://127.0.0.1:8000", follow_redirects=False) as test_client:
        yield test_client


@pytest.fixture
def onboarded(db):
    db.get(AppSettings, 1).onboarding_done = True
    db.commit()


def _minimal_pdf(text: str) -> bytes:
    """A one-page PDF containing `text`, built by hand so tests need no PDF-writing library."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    return bytes(out)


@pytest.fixture
def make_pdf():
    return _minimal_pdf
