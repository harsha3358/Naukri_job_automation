import logging
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.config import config
from backend.db.models import CV, CandidateProfile
from backend.services.cv_parser import SUPPORTED_SUFFIXES, CVReadError, extract_text, parse_cv

log = logging.getLogger(__name__)

_PARSED_FIELDS = ("full_name", "email", "phone", "experience_years", "skills", "education")
_EMPTY = ("", None, [])


def store_cv(db: Session, filename: str, data: bytes) -> CV:
    """Save an uploaded CV, read it and make it the active one.

    Raises CVReadError with a message that is safe to show to the user.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise CVReadError("Please choose a PDF, DOCX or TXT file.")
    if not data:
        raise CVReadError("That file is empty.")
    if len(data) > config.max_cv_size_mb * 1024 * 1024:
        raise CVReadError(f"That file is larger than {config.max_cv_size_mb} MB.")

    # Our own name on disk: the uploaded name is never trusted as a path.
    stored_name = f"{uuid4().hex}{suffix}"
    path = config.resumes_dir / stored_name
    path.write_bytes(data)
    try:
        text = extract_text(path)
        if not text.strip():
            raise CVReadError(
                "No text could be read from this file. If it is a scanned image, "
                "export your CV as a normal PDF or DOCX and try again."
            )
    except CVReadError:
        path.unlink(missing_ok=True)
        raise

    parsed = asdict(parse_cv(text))
    db.execute(update(CV).values(is_active=False))
    cv = CV(
        original_name=Path(filename).name[:255],
        stored_name=stored_name,
        parsed_text=text,
        parsed=parsed,
        is_active=True,
    )
    db.add(cv)
    fill_profile(db.get(CandidateProfile, 1), parsed, overwrite=False)
    db.commit()
    log.info("CV stored: %s (%d skills found)", cv.original_name, len(parsed["skills"]))
    return cv


def fill_profile(profile: CandidateProfile, parsed: dict, *, overwrite: bool) -> None:
    """Copy details read from a CV into the profile. Without overwrite, only empty fields are filled."""
    for name in _PARSED_FIELDS:
        value = parsed.get(name)
        if value in _EMPTY:
            continue
        if overwrite or getattr(profile, name) in _EMPTY:
            setattr(profile, name, value)


def activate_cv(db: Session, cv: CV) -> None:
    db.execute(update(CV).values(is_active=False))
    cv.is_active = True
    db.commit()


def delete_cv(db: Session, cv: CV) -> None:
    was_active = cv.is_active
    (config.resumes_dir / cv.stored_name).unlink(missing_ok=True)
    db.delete(cv)
    db.flush()
    if was_active:
        latest = db.scalars(select(CV).order_by(CV.uploaded_at.desc()).limit(1)).first()
        if latest:
            latest.is_active = True
    db.commit()
