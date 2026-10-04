from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.web import read_upload, redirect, render
from backend.db.database import get_db
from backend.db.models import CV, CandidateProfile
from backend.services.cv_parser import CVReadError
from backend.services.cv_store import activate_cv, delete_cv, fill_profile, store_cv

router = APIRouter(prefix="/cv")


def _page(request: Request, db: Session, *, error: str = "", status_code: int = 200):
    cvs = db.scalars(select(CV).order_by(CV.uploaded_at.desc())).all()
    return render(
        request,
        "cv.html",
        status_code=status_code,
        active="cv",
        error=error,
        active_cv=next((cv for cv in cvs if cv.is_active), None),
        other_cvs=[cv for cv in cvs if not cv.is_active],
    )


def _get_cv(db: Session, cv_id: int) -> CV:
    cv = db.get(CV, cv_id)
    if cv is None:
        raise HTTPException(status_code=404, detail="CV not found")
    return cv


@router.get("")
def cv_page(request: Request, db: Session = Depends(get_db)):
    return _page(request, db)


@router.post("/upload")
def upload(request: Request, file: UploadFile | None = None, db: Session = Depends(get_db)):
    try:
        store_cv(db, *read_upload(file))
    except CVReadError as exc:
        return _page(request, db, error=str(exc), status_code=400)
    return redirect("/cv", "cv_uploaded")


@router.post("/{cv_id}/activate")
def activate(cv_id: int, db: Session = Depends(get_db)):
    activate_cv(db, _get_cv(db, cv_id))
    return redirect("/cv", "cv_active")


@router.post("/{cv_id}/use-in-profile")
def use_in_profile(cv_id: int, db: Session = Depends(get_db)):
    fill_profile(db.get(CandidateProfile, 1), _get_cv(db, cv_id).parsed, overwrite=True)
    db.commit()
    return redirect("/profile", "profile_filled")


@router.post("/{cv_id}/delete")
def delete(cv_id: int, db: Session = Depends(get_db)):
    delete_cv(db, _get_cv(db, cv_id))
    return redirect("/cv", "deleted")
