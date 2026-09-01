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

import asyncio
import queue
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


# ---------------------------------------------------------------------------
# A single stdin reader for the whole process.
# ---------------------------------------------------------------------------

_reader_thread: Optional[threading.Thread] = None
_line_queue: "queue.Queue[Optional[str]]" = queue.Queue()
_reader_started = threading.Event()


def _reader_loop() -> None:
    """Read stdin forever, handing each line to whoever is waiting.

    Deliberately not cancellable: a blocked stdin read cannot be
    interrupted, so the answer is to only ever have one of them.
    """
    while True:
        try:
            line = sys.stdin.readline()
        except Exception:
            _line_queue.put(None)
            return
        if line == "":  # EOF - stdin closed
            _line_queue.put(None)
            return
        _line_queue.put(line.rstrip("\r\n"))


def start_reader() -> None:
    """Start the stdin reader once. Safe to call repeatedly."""
    global _reader_thread
    with _LOCK:
        if _reader_thread is not None and _reader_thread.is_alive():
            return
        _reader_thread = threading.Thread(
            target=_reader_loop, name="stdin-reader", daemon=True,
        )
        _reader_thread.start()
        _reader_started.set()


def _blocking_next_line(prompt: str) -> Optional[str]:
    """Draw the prompt and wait for the reader to deliver a line."""
    start_reader()
    set_prompt(prompt)
    _write(prompt)
    try:
        while True:
            try:
                return _line_queue.get(timeout=0.2)
            except queue.Empty:
                continue
    finally:
        set_prompt(None)


# A line the reader delivered to a read that was cancelled before it could
# receive it. Handed to the next caller instead of being discarded.
_stashed: Optional[str] = None
_stash_is_set = False


def _take_stash():
    """Pop the stashed line, if there is one. Returns (found, value)."""
    global _stashed, _stash_is_set
    with _LOCK:
        if _stash_is_set:
            value, _stashed, _stash_is_set = _stashed, None, False
            return True, value
    return False, None


def _put_stash(value) -> None:
    global _stashed, _stash_is_set
    with _LOCK:
        _stashed, _stash_is_set = value, True


async def read_line(prompt: str) -> Optional[str]:
    """Await one line of input without ever losing a keystroke.

    Returns None when stdin closes. Cancelling this cancels only the wait:
    the reader thread carries on, and a line that arrives during the
    cancellation is stashed for the next caller rather than dropped.
    """
    found, value = _take_stash()
    if found:
        return value

    start_reader()
    set_prompt(prompt)
    _write(prompt)
    loop = asyncio.get_running_loop()
    try:
        while True:
            found, value = _take_stash()
            if found:
                return value
            future = loop.run_in_executor(None, _line_queue.get, True, 0.2)
            try:
                # Shielded: if this read is cancelled, the executor call
                # still completes and the callback below keeps its result.
                return await asyncio.shield(future)
            except queue.Empty:
                continue
            except asyncio.CancelledError:
                def _keep(done):
                    try:
                        _put_stash(done.result())
                    except Exception:
                        pass  # Empty, or the executor failed - nothing to keep
                future.add_done_callback(_keep)
                raise
    finally:
        set_prompt(None)


def drain_pending() -> None:
    """Discard anything typed ahead. Used when abandoning a prompt."""
    _take_stash()
    while True:
        try:
            _line_queue.get_nowait()
        except queue.Empty:
            return
