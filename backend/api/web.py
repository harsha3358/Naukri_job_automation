"""Shared helpers for the server-rendered pages."""

import math
from collections.abc import Callable

from fastapi import Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.config import PROJECT_ROOT, config
from backend.core.clock import to_local

templates = Jinja2Templates(directory=PROJECT_ROOT / "dashboard" / "templates")
templates.env.filters["localtime"] = lambda value: to_local(value).strftime("%d %b %Y, %H:%M")
# Numbers for form fields and tables: None -> "", 2.0 -> "2", 2.5 -> "2.5".
templates.env.filters["num"] = lambda value: "" if value is None else f"{value:g}"
templates.env.globals["max_cv_size_mb"] = config.max_cv_size_mb
# Added to CSS/JS links so browsers fetch new files after an update instead of using cached ones.
templates.env.globals["static_version"] = int(
    max(path.stat().st_mtime for path in (PROJECT_ROOT / "dashboard" / "static").iterdir())
)
# What each application state is called on screen.
templates.env.globals["state_labels"] = {
    "discovered": "Found",
    "skipped": "Skipped",
    "queued": "Waiting to apply",
    "applying": "Applying",
    "applied": "Applied",
    "failed": "Failed",
    "needs_manual": "Apply by hand",
    "external": "Apply on company site",
}

# Shown after a redirect as ?msg=<key>. Keys only, so no free text travels in the URL.
NOTICES = {
    "saved": "Saved.",
    "added": "Added.",
    "deleted": "Deleted.",
    "cv_uploaded": "CV uploaded and read. Check the details below.",
    "cv_active": "That CV is now the active one.",
    "profile_filled": "Profile updated from your CV.",
    "demo_loaded": "Sample jobs loaded. One of them was a repeat and was ignored, which is duplicate protection at work.",
    "demo_removed": "Sample jobs removed.",
    "demo_needs_role": "Add a role on the Roles page first. The sample jobs are built around it.",
    "sheet_connected": "Your Google Sheet is connected. Applications so far were sent to it; open the Sheet to see them.",
    "sheet_sent": "Sent. Your Google Sheet is up to date.",
    "busy": "The tool is already using its browser window. Wait for it to finish, then try again.",
}


class FormError(Exception):
    """A form value was not acceptable. The message is shown to the user."""


def render(request: Request, template: str, *, status_code: int = 200, **context) -> HTMLResponse:
    context.setdefault("notice", NOTICES.get(request.query_params.get("msg", "")))
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def redirect(path: str, msg: str = "") -> RedirectResponse:
    # 303 so the browser follows a POST with a GET.
    return RedirectResponse(f"{path}?msg={msg}" if msg else path, status_code=303)


def split_list(value: str) -> list[str]:
    """Comma- or line-separated text to a clean list, dropping blanks and repeats."""
    items: list[str] = []
    seen: set[str] = set()
    for part in value.replace("\n", ",").split(","):
        item = " ".join(part.split())
        if item and item.lower() not in seen:
            seen.add(item.lower())
            items.append(item)
    return items


def optional_number(value: str, cast: Callable, label: str, *, maximum: float | None = None):
    """Blank -> None. Otherwise a non-negative number, or FormError."""
    value = value.strip()
    if not value:
        return None
    try:
        number = cast(value)
    except ValueError:
        kind = "a whole number" if cast is int else "a number"
        raise FormError(f"{label} must be {kind}.") from None
    if not math.isfinite(number) or number < 0:
        raise FormError(f"{label} cannot be negative.")
    if maximum is not None and number > maximum:
        raise FormError(f"{label} cannot be more than {maximum:g}.")
    return number


def read_upload(file: UploadFile | None) -> tuple[str, bytes]:
    """Name and content of an uploaded file. `file` is None when the form was sent with no file chosen.

    Reads at most one byte past the size limit, so an oversized file is detected without loading it all.
    """
    if file is None:
        return "", b""
    return file.filename or "", file.file.read(config.max_cv_size_mb * 1024 * 1024 + 1)
