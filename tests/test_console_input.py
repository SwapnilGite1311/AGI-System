"""The interactive prompt must never swallow what the user typed.

The reported symptom was "after few commands it stucked again wasn't able
to enter the input": you type, and nothing happens.

The cause was one reader thread per prompt. `asyncio.to_thread(input, ...)`
can have its *await* cancelled, but the thread it started cannot be - it
stays blocked inside stdin. Ctrl+C in voice mode does `continue`, so the
loop immediately started another reader, and the orphan was still there
competing for keystrokes. Whichever one won, nobody was awaiting it, so the
line vanished. It accumulated over a session, which is why it got worse the
longer the terminal stayed open.
"""

import asyncio
import io
import sys
import threading
import time

import pytest

ROOT = __import__('pathlib').Path(__file__).resolve().parent.parent


class SlowStdin(io.TextIOBase):
    """stdin that blocks between lines, the way a terminal does."""

    def __init__(self, lines, delay=0.3):
        self._lines = list(lines)
        self._delay = delay
        self._lock = threading.Lock()

    def readline(self):
        time.sleep(self._delay)
        with self._lock:
            if not self._lines:
                time.sleep(30)  # block like an idle terminal
                return ""
            return self._lines.pop(0)


@pytest.fixture
def console_with_stdin(monkeypatch):
    """A freshly-reset console module reading from a scripted stdin."""
    from core import console

    def _install(lines):
        console.drain_pending()
        monkeypatch.setattr(sys, "stdin", SlowStdin(lines))
        return console

    yield _install
    from core import console as c
    c.drain_pending()


def test_abandoned_prompts_do_not_swallow_input(console_with_stdin):
    """Three cancelled reads must lose nothing.

    This is the actual bug: before the fix, all three lines were consumed
    by orphaned threads and silently discarded.
    """
    console = console_with_stdin(["alpha\n", "beta\n", "gamma\n"])

    async def scenario():
        for _ in range(3):
            task = asyncio.create_task(console.read_line("You: "))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        got = []
        for _ in range(3):
            try:
                got.append(await asyncio.wait_for(console.read_line("You: "), timeout=8))
            except asyncio.TimeoutError:
                break
        return got

    received = asyncio.run(scenario())
    assert received == ["alpha", "beta", "gamma"], (
        f"input was swallowed by an abandoned reader: got {received}")


def test_only_one_reader_thread_ever_exists(console_with_stdin):
    """However many prompts are abandoned, stdin has exactly one owner."""
    console = console_with_stdin(["one\n", "two\n"])

    async def scenario():
        for _ in range(5):
            task = asyncio.create_task(console.read_line("You: "))
            await asyncio.sleep(0.02)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await asyncio.sleep(0.2)

    asyncio.run(scenario())
    readers = [t for t in threading.enumerate() if t.name == "stdin-reader"]
    assert len(readers) == 1, (
        f"{len(readers)} reader threads are competing for stdin")


def test_closed_stdin_reports_eof():
    """A closed stdin must end the session, not hang the prompt.

    Runs in its own process: the reader owns stdin for the life of the
    process by design, so a test that swapped stdin underneath a reader
    already parked on the previous one would be testing an arrangement
    that cannot occur in a real session.
    """
    import subprocess
    import textwrap

    script = textwrap.dedent(f"""
        import asyncio, io, sys
        sys.path.insert(0, {str(ROOT)!r})

        class ClosedStdin(io.TextIOBase):
            def readline(self):
                return ""

        sys.stdin = ClosedStdin()
        from core import console

        async def main():
            return await asyncio.wait_for(console.read_line("You: "), timeout=10)

        print("EOF_RESULT:", asyncio.run(main()))
    """)
    proc = subprocess.run([sys.executable, "-c", script],
                          capture_output=True, text=True, timeout=60)
    assert "EOF_RESULT: None" in proc.stdout, (
        f"EOF did not surface as None. stdout={proc.stdout!r} "
        f"stderr={proc.stderr!r}")
