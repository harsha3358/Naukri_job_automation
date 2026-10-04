from fastapi import APIRouter

from backend.api.web import redirect
from backend.workers import runner
from backend.workers.apply import run_apply
from backend.workers.connect import run_connect
from backend.workers.discover import run_discovery

router = APIRouter(prefix="/naukri")


@router.post("/search")
def search():
    started = runner.start("search", run_discovery)
    return redirect("/jobs", "" if started else "busy")  # the Jobs page itself shows a search in progress


@router.post("/apply")
def apply():
    started = runner.start("apply", run_apply)
    return redirect("/jobs", "" if started else "busy")  # the Jobs page itself shows a run in progress


@router.post("/connect")
def connect():
    started = runner.start("connect", run_connect)
    return redirect("/settings", "" if started else "busy")  # the Settings page shows the login in progress
