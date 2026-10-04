from playwright.sync_api import Page

from backend.config import config
from backend.core.clock import utcnow


def save_evidence(page: Page, label: str) -> str:
    """Keep a picture and the HTML of a page the tool could not handle. Returns the picture's path."""
    folder = config.data_dir / "screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / f"{label}-{utcnow():%Y%m%d-%H%M%S}"
    page.screenshot(path=f"{stem}.png", full_page=True)
    stem.with_suffix(".html").write_text(page.content(), encoding="utf-8")
    return f"{stem}.png"
