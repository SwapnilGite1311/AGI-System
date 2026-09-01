"""Speech must never be able to freeze the prompt.

This is a regression test for a hang caught in a real session. The
interactive loop did:

    await asyncio.to_thread(self._speak_result, result)

with no timeout, and behind that sat a 60-second HTTP call to the local
voice server followed by `winsound.PlaySound`, which is synchronous and
has no timeout at all. When speech stalled, the loop never came back to
the prompt.

The captured evidence, from logs.txt: a Google Form command completed
successfully, then two further commands were typed and never processed,
and the process turned out to be parked here -

    main.py line 6005, in run_interactive
        await asyncio.to_thread(self._speak_result, result)
    asyncio.exceptions.CancelledError

escaping only when the user pressed Ctrl+C. The user's reading was that
the *next* command had hung; in fact the session had already been dead
since the previous one, and everything typed after went into a prompt
nobody was reading.

Speech is cosmetic, the prompt is the product, so speech now runs on its
own thread behind a bounded queue and the loop never waits for it.
"""

import threading
import time

import pytest

from core import speech


@pytest.fixture(autouse=True)
def _fresh_speech_queue():
    """Each test gets a quiet queue and leaves one behind."""
    speech.shutdown()
    yield
    speech.shutdown()


def test_say_returns_immediately_even_when_synthesis_hangs():
    """The actual bug: a synthesiser that never returns.

    Before the fix this was awaited inline, so the prompt never came back.
    """
    started = threading.Event()

    def hangs_forever(text):
        started.set()
        time.sleep(3600)

    speech.configure(hangs_forever)

    began = time.perf_counter()
    for index in range(6):
        speech.say(f"utterance {index}")
    elapsed = time.perf_counter() - began

    assert elapsed < 1.0, (
        f"say() took {elapsed:.2f}s with a hung synthesiser - it must never "
        "wait on synthesis, that is the whole point")
    assert started.wait(timeout=5), "the speech worker never picked anything up"


def test_backlog_is_bounded_so_a_long_session_cannot_grow_one():
    """Talking is slower than typing, so the queue must drop, not grow."""

    def slow(text):
        time.sleep(30)

    speech.configure(slow)
    for index in range(50):
        speech.say(f"utterance {index}")

    assert speech.pending() <= 2, (
        f"{speech.pending()} utterances queued - a backlog can build up")
    assert speech.dropped() > 0, "nothing was dropped, so the bound is not working"


def test_shutdown_does_not_wait_for_a_stuck_utterance():
    """A stuck utterance must not hold up the exit either."""

    def hangs_forever(text):
        time.sleep(3600)

    speech.configure(hangs_forever)
    speech.say("something")
    time.sleep(0.2)  # let the worker pick it up and get stuck

    began = time.perf_counter()
    speech.shutdown(timeout=1.0)
    elapsed = time.perf_counter() - began

    assert elapsed < 2.0, f"shutdown blocked for {elapsed:.2f}s on a stuck utterance"


def test_synthesis_failure_is_swallowed():
    """Speech failing is the least important thing that can happen."""
    calls = []

    def explodes(text):
        calls.append(text)
        raise RuntimeError("no audio device")

    speech.configure(explodes)
    speech.say("first")
    time.sleep(0.4)
    speech.say("second")
    time.sleep(0.4)

    assert calls == ["first", "second"], (
        f"the worker died on the first failure instead of carrying on: {calls}")


def test_empty_text_is_not_queued():
    spoken = []
    speech.configure(spoken.append)
    assert speech.say("") is False
    assert speech.say("   ") is False
    time.sleep(0.2)
    assert spoken == []
