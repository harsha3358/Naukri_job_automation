from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.web import redirect, render
from backend.db.database import get_db
from backend.db.models import Answer

router = APIRouter(prefix="/answers")


def _page(request: Request, db: Session, *, error: str = "", status_code: int = 200):
    return render(
        request,
        "answers.html",
        status_code=status_code,
        active="answers",
        error=error,
        answers=db.scalars(select(Answer).order_by(Answer.id)).all(),
    )


@router.get("")
def answers_page(request: Request, db: Session = Depends(get_db)):
    return _page(request, db)


@router.post("")
def add_answer(
    request: Request,
    question: Annotated[str, Form()] = "",
    answer: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    question, answer = " ".join(question.split()), answer.strip()
    if not question or not answer:
        return _page(request, db, error="Please fill in both the question and the answer.", status_code=400)
    db.add(Answer(question=question[:300], answer=answer[:500]))
    db.commit()
    return redirect("/answers", "added")


@router.post("/{answer_id}/delete")
def delete_answer(answer_id: int, db: Session = Depends(get_db)):
    answer = db.get(Answer, answer_id)
    if answer is not None:
        db.delete(answer)
        db.commit()
    return redirect("/answers", "deleted")
