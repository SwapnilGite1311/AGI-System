"""The status line must never be the reason something breaks.

It is decoration around real work: it tells the user the difference
between "working" and "hung". That makes it valuable, and it also makes it
the kind of thing that must fail silently, because nobody should lose a
command to a spinner.
"""

import io
import sys
import time

import pytest

from core import progress


class FakeTTY(io.StringIO):
    """Looks like a terminal, so the module will actually draw."""
    encoding = "utf-8"

    def isatty(self):
        return True


@pytest.fixture(autouse=True)
def _always_stop():
    yield
    progress.stop()
    progress.set_enabled(True)


def test_silent_when_output_is_not_a_terminal(capsys):
    """Piped output and test runs must not fill up with carriage returns."""
    progress.start("Thinking")
    progress.update("Still thinking")
    time.sleep(0.3)
    progress.stop()
    assert capsys.readouterr().out == "", "drew to a non-terminal stdout"


def test_draws_and_updates_on_a_terminal(monkeypatch):
    fake = FakeTTY()
    monkeypatch.setattr(sys, "stdout", fake)

    progress.start("Thinking")
    time.sleep(0.35)
    progress.update("Opening the page")
    time.sleep(0.35)
    progress.stop()

    out = fake.getvalue()
    assert "Thinking" in out
    assert "Opening the page" in out, "update() did not change the message"


def test_stop_is_safe_without_start():
    progress.stop()
    progress.stop()


def test_update_without_start_does_nothing(monkeypatch):
    fake = FakeTTY()
    monkeypatch.setattr(sys, "stdout", fake)
    progress.update("orphaned message")
    time.sleep(0.2)
    assert fake.getvalue() == "", "update() drew without an active line"


def test_a_broken_stdout_does_not_propagate(monkeypatch):
    """If the console cannot be written to, that is not the command's problem."""

    class ExplodingTTY(io.StringIO):
        encoding = "utf-8"

        def isatty(self):
            return True

        def write(self, *a, **kw):
            raise OSError("console is gone")

    monkeypatch.setattr(sys, "stdout", ExplodingTTY())
    progress.start("Thinking")   # must not raise
    time.sleep(0.3)
    progress.update("Still here")
    progress.stop()


def test_nested_steps_restore_the_outer_message(monkeypatch):
    fake = FakeTTY()
    monkeypatch.setattr(sys, "stdout", fake)

    with progress.step("Working through the steps"):
        time.sleep(0.25)
        with progress.step("Searching the web"):
            time.sleep(0.25)
        time.sleep(0.25)

    out = fake.getvalue()
    assert "Searching the web" in out
    assert out.count("Working through the steps") > 0
    assert progress._active is False, "the line was left running after the block"


def test_disabled_draws_nothing(monkeypatch):
    fake = FakeTTY()
    monkeypatch.setattr(sys, "stdout", fake)
    progress.set_enabled(False)
    progress.start("Thinking")
    time.sleep(0.25)
    progress.stop()
    assert fake.getvalue() == ""
