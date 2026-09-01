"""Speech that can never hold up the prompt.

The interactive loop used to do:

    await asyncio.to_thread(self._speak_result, result)

with no timeout, and the speech path behind it is a 60-second HTTP call to
the local voice server followed by `winsound.PlaySound`, which is
synchronous and has no timeout at all. So anything that stalled in there -
a slow voice server, a malformed WAV, an audio device still held by the
recording path - froze the prompt permanently. The observed symptom was
exactly that: a command completes, prints its result, and the "You: "
prompt never comes back. Typing after that does nothing, because nothing
is reading.

The priority ordering was backwards. Speech is cosmetic; the prompt is
the product. So speech now runs on its own dedicated thread behind a
queue, and the loop hands text over and returns immediately.

Two more properties that matter for a long session:

  - The queue is bounded. If speech falls behind - which it does, since
    talking is far slower than typing - the OLDEST pending utterance is
    dropped rather than letting a backlog grow forever. Hearing the
    response to your last command matters; hearing the one from four
    commands ago does not.
  - The engine is only ever driven from this one thread. pyttsx3 on
    Windows wraps SAPI, which is COM, and COM objects are thread-affine.
    Keeping a single owner sidesteps that whole class of problem rather
    than hoping the thread pool happens to reuse a worker.
"""

import queue
import threading
from typing import Callable, Optional

from loguru import logger

# Enough to keep a sentence or two in flight, small enough that a backlog
# cannot build up while someone types faster than the machine can talk.
_MAX_PENDING = 2

_queue: "queue.Queue[str]" = queue.Queue()
_worker: Optional[threading.Thread] = None
_lock = threading.RLock()
_speak_fn: Optional[Callable[[str], None]] = None
_dropped = 0

# Stopping is signalled out of band. Pushing a sentinel into the queue that
# carries text meant a leftover sentinel could outlive its worker and kill
# the next one on its first read.
_stop = threading.Event()


def _drain() -> None:
    """Discard anything queued. Caller holds the lock."""
    while True:
        try:
            _queue.get_nowait()
        except queue.Empty:
            return


def _run(stop: threading.Event) -> None:
    """Drain the queue until asked to stop, one utterance at a time."""
    while not stop.is_set():
        try:
            text = _queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if stop.is_set():
            return
        speak_fn = _speak_fn
        if speak_fn is None:
            continue
        try:
            speak_fn(text)
        except Exception as exc:
            # Speech failing must never propagate anywhere. It is the least
            # important thing happening.
            logger.debug("Speech failed ({}): {}", type(exc).__name__, str(exc)[:120])


def configure(speak_fn: Callable[[str], None]) -> None:
    """Set the function that actually produces sound, and start the worker."""
    global _worker, _speak_fn
    with _lock:
        _speak_fn = speak_fn
        if _worker is not None and _worker.is_alive():
            return
        _stop.clear()
        _drain()  # nothing from a previous run should be spoken now
        _worker = threading.Thread(
            target=_run, args=(_stop,), name="speech", daemon=True)
        _worker.start()


def say(text: str) -> bool:
    """Queue `text` to be spoken. Returns immediately, always.

    False means the utterance was dropped because speech is behind - which
    is a normal outcome, not an error.
    """
    global _dropped
    if not text or not text.strip():
        return False
    if _speak_fn is None:
        return False

    with _lock:
        while _queue.qsize() >= _MAX_PENDING:
            try:
                _queue.get_nowait()  # drop the oldest, keep the newest
                _dropped += 1
            except queue.Empty:
                break
        _queue.put(text)
    return True


def pending() -> int:
    """How many utterances are waiting."""
    return _queue.qsize()


def dropped() -> int:
    """How many were discarded to keep the queue short."""
    return _dropped


def shutdown(timeout: float = 2.0) -> None:
    """Stop the worker. Never blocks for long - a stuck utterance must not
    hold up the exit any more than it holds up the prompt."""
    global _worker
    with _lock:
        _stop.set()
        _drain()
        worker, _worker = _worker, None
    if worker is not None and worker.is_alive():
        worker.join(timeout=timeout)
