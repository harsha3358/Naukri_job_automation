import logging
from logging.handlers import RotatingFileHandler

from backend.config import config

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging() -> None:
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return

    config.logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        config.logs_dir / "app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(LOG_FORMAT))

    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console)
