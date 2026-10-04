"""Runs one browser task at a time in the background.

The tool's browser profile can be open in only one browser, and the user should see only one
tool window, so searching, connecting and (later) applying all take turns through here.
"""

import logging
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

_busy = threading.Lock()
_current = ""


def start(name: str, task: Callable[[], None]) -> bool:
    """Start `task` on its own thread. False if another task is still running."""
    global _current
    if not _busy.acquire(blocking=False):
        return False
    _current = name

    def run() -> None:
        global _current
        try:
            task()
        except Exception:  # the last line of defence: a crash here must not leave the tool stuck "busy"
            log.exception("Background task %r crashed", name)
        finally:
            _current = ""
            _busy.release()

    threading.Thread(target=run, name=name, daemon=True).start()
    return True


def current() -> str:
    """Name of the running task, or "" when idle."""
    return _current
