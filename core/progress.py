"""A live status line, so the user can tell the difference between
"working" and "hung".

Until now a command printed nothing between the moment it was typed and
the moment it finished. A command that takes six seconds and a command
that has deadlocked look identical from the outside - which is exactly
how a hang in the speech path went unnoticed for a whole testing session:
the prompt simply stopped coming back, and there was no way to tell that
from slowness.

Two things this buys, and the second matters more:

  - Honesty. If the system is searching the web, it says so. The user can
    see progress is being made, and roughly where.
  - Perceived speed. A visible elapsed counter feels far faster than the
    same wait against a blank screen, because the uncertainty is what is
    unpleasant, not the seconds.

Deliberately quiet about its own failures: this is decoration around the
real work, and it must never be the reason a command breaks. Every write
is guarded, and when stdout is not a terminal - piped output, a test run,
a captured log - it disables itself entirely rather than filling the file
with carriage returns.
"""

import itertools
import sys
import threading
import time
from typing import Optional

from core import console

# Braille spinner: dense, single-width, and renders in Windows Terminal.
# Falls back to ASCII where the encoding cannot take it.
_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_ASCII_FRAMES = "|/-\\"

_lock = threading.RLock()
_thread: Optional[threading.Thread] = None
_stop = threading.Event()
_message = ""
_started_at = 0.0
_enabled = True
_active = False


def _interactive() -> bool:
    """Only draw when a person is actually watching."""
    try:
        return bool(_enabled and sys.stdout.isatty())
    except Exception:
        return False


def _frames() -> str:
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return _FRAMES if "utf" in encoding else _ASCII_FRAMES


def _clear_line() -> None:
    try:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
    except Exception:
        pass


def _run() -> None:
    spinner = itertools.cycle(_frames())
    while not _stop.is_set():
        with _lock:
            text, since = _message, _started_at
        if text:
            elapsed = time.time() - since
            # Seconds only appear after a second, so quick commands do not
            # flash a counter at the user for no reason.
            suffix = f" {elapsed:.0f}s" if elapsed >= 1.0 else ""
            try:
                sys.stdout.write(f"\r\033[K  {next(spinner)} {text}{suffix}")
                sys.stdout.flush()
            except Exception:
                return  # a console we cannot draw on is not worth retrying
        _stop.wait(0.12)
    _clear_line()


def start(message: str) -> None:
    """Begin showing `message` with a spinner. Safe to call repeatedly."""
    global _thread, _message, _started_at, _active
    if not _interactive():
        return
    with _lock:
        _message = message
        _started_at = time.time()
        _active = True
        if _thread is not None and _thread.is_alive():
            return
        _stop.clear()
        _thread = threading.Thread(target=_run, name="progress", daemon=True)
        _thread.start()
    # The prompt is not on screen while we are drawing over its line.
    console.set_prompt(None)


def update(message: str) -> None:
    """Change what the status line says, keeping the elapsed clock running.

    The clock deliberately does NOT reset: the user cares how long they
    have been waiting in total, not how long this particular phase has
    taken.
    """
    global _message
    if not _active:
        return
    with _lock:
        _message = message


def stop() -> None:
    """Remove the status line and leave the cursor at column zero."""
    global _thread, _message, _active
    with _lock:
        if _thread is None and not _active:
            return
        _active = False
        _message = ""
        _stop.set()
        thread, _thread = _thread, None
    if thread is not None and thread.is_alive():
        thread.join(timeout=0.5)
    _clear_line()


def set_enabled(enabled: bool) -> None:
    """Turn the whole thing off, for callers that manage their own output."""
    global _enabled
    _enabled = bool(enabled)
    if not enabled:
        stop()


class step:
    """Context manager: show a message for the duration of a block.

        with progress.step("Searching the web"):
            ...

    Nested use is fine - the inner message replaces the outer one and the
    outer is restored on exit, so a long phase made of short ones still
    reads sensibly.
    """

    def __init__(self, message: str):
        self.message = message
        self._previous = ""
        self._owned = False

    def __enter__(self):
        global _active
        self._previous = _message
        if _active:
            update(self.message)
        else:
            self._owned = True
            start(self.message)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._owned:
            stop()
        elif self._previous:
            update(self._previous)
        return False
