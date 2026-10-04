import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.api import answers, cv, jobs, naukri, overview, profile, roles, settings, welcome
from backend.config import PROJECT_ROOT, config
from backend.core.log import setup_logging
from backend.db.database import init_db
from backend.services import registration, sheets_sync

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    init_db()
    log.info("Started. Data folder: %s", config.data_dir)
    registration.send_pending_in_background()  # retries a send that failed last time
    sheets_sync.sync_in_background()  # likewise for rows the Sheet has not received yet
    yield


app = FastAPI(title="Naukri Job Automation", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

# This app runs on the user's own PC and will act on their Naukri account, so only the local
# browser may talk to it: reject foreign Host headers and cross-site form posts.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])


@app.middleware("http")
async def block_cross_site_writes(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            return PlainTextResponse("Cross-site request blocked.", status_code=403)
    return await call_next(request)


app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "dashboard" / "static"), name="static")

for module in (overview, welcome, cv, profile, roles, answers, jobs, settings, naukri):
    app.include_router(module.router)
