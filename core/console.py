"""
One place that owns stdout while an input() prompt is pending.

Background workers (the reminder loop, the remote-queue worker, memory
maintenance) print while the interactive prompt is waiting for the user.
Their output landed in the middle of the typed line, so the session log
shows things like:

    You:
    [REMINDER] REMINDER: Test Reminder - Test reminder description
    hey there how are you today?

and after a command whose result printed late, the "You: " prompt scrolled
away entirely - a 17-minute stretch in one recorded session where the user
could not tell the terminal was still accepting input.

The fix is not to silence background output but to make it cooperate:
anything printed while a prompt is live clears the prompt line first, then
reprints the prompt underneath along with whatever the user had typed so
far, so the caret is always visibly where typing goes.
"""

import sys
import threading
from typing import Optional

_LOCK = threading.RLock()
_active_prompt: Optional[str] = None


def _write(text: str) -> None:
    """Write without letting an encoding error kill the caller."""
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        try:
            sys.stdout.write(safe)
            sys.stdout.flush()
        except Exception:
            pass
    except Exception:
        pass


def set_prompt(prompt: Optional[str]) -> None:
    """Record that `prompt` is currently displayed and awaiting input."""
    global _active_prompt
    with _LOCK:
        _active_prompt = prompt


def safe_print(text: str = "", end: str = "\n") -> None:
    """Print without corrupting a pending input prompt.

    Callers on background threads use this instead of print(). When a prompt
    is live, the prompt line is erased, the message is written, and the
    prompt is redrawn so the user can see where to type.
    """
    with _LOCK:
        prompt = _active_prompt
        if prompt:
            # \r + erase-to-end-of-line: wipe the prompt we drew.
            _write("\r\033[K")
        _write(f"{text}{end}")
        if prompt:
            _write(prompt)


def prompt_input(prompt: str) -> str:
    """input() that cooperates with safe_print from other threads."""
    set_prompt(prompt)
    try:
        return input(prompt)
    finally:
        set_prompt(None)
