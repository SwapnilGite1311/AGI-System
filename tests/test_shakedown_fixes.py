"""Regressions for the issues found in the 2026-08-29 live shakedown.

Every test here corresponds to something that actually went wrong in a real
session, recorded in logs.txt.
"""

import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import AutonomousSystemController as ASC  # noqa: E402


def render(payload) -> str:
    controller = object.__new__(ASC)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        controller._display_step_result(payload)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# 1. The renderer dropped anything it had no hardcoded branch for.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("payload,expected", [
    ({"drives": [{"device": "C:", "free_gb": 159}]}, "C:"),
    ({"tasks": [{"title": "call supplier", "status": "pending"}]}, "call supplier"),
    ({"team_members": [{"name": "Alice", "role": "manager"}]}, "Alice"),
    ({"audit_trail": [{"event_type": "tenant_created"}]}, "tenant_created"),
    ({"summary": {"total_tasks": 453}}, "453"),
])
def test_results_are_never_silently_dropped(payload, expected):
    """list tasks / list team / disk drives ran fine and printed nothing.

    _display_step_result knew 11 hardcoded keys and had no else branch, so
    five working features looked broken: they reported "completed
    successfully" above a blank screen.
    """
    payload["success"] = True
    assert expected in render(payload)


def test_handled_shapes_are_not_double_printed():
    """The fallback must not re-print what an explicit branch already showed."""
    out = render({"success": True, "message": "Screenshot captured."})
    assert out.count("Screenshot captured.") == 1


def test_bookkeeping_fields_are_not_shown_to_the_user():
    out = render({"success": True, "tier": "direct", "source": "rules",
                  "drives": [{"device": "C:"}]})
    assert "tier" not in out.lower()
    assert "source" not in out.lower()


# --------------------------------------------------------------------------
# 2. Background output landed inside the input prompt.
# --------------------------------------------------------------------------

def test_background_output_redraws_the_prompt():
    """A reminder printed mid-prompt made the terminal look dead.

    Recorded session:
        You:
        [REMINDER] REMINDER: Test Reminder - Test reminder description
        hey there how are you today?
    """
    from core import console

    buffer = io.StringIO()
    original = sys.stdout
    try:
        sys.stdout = buffer
        console.set_prompt("You: ")
        console._write("You: ")
        console.safe_print("[REMINDER] something happened")
        console.set_prompt(None)
    finally:
        sys.stdout = original

    out = buffer.getvalue()
    assert "[REMINDER] something happened" in out
    assert "\r\033[K" in out, "prompt line was not cleared first"
    assert out.rstrip().endswith("You:"), "prompt was not redrawn underneath"


def test_safe_print_survives_an_unencodable_console():
    """An emoji must never abort the printing path."""
    from core import console

    class Cp1252:
        encoding = "cp1252"

        def write(self, text):
            text.encode("cp1252")
            return len(text)

        def flush(self):
            pass

    original = sys.stdout
    try:
        sys.stdout = Cp1252()
        console.safe_print("reminder ⏰ with emoji")   # must not raise
    finally:
        sys.stdout = original


# --------------------------------------------------------------------------
# 3. A detected mismatch was announced as a success.
# --------------------------------------------------------------------------

def test_a_detected_mismatch_is_not_announced_as_success():
    """It printed "completed successfully" and then contradicted itself.

    Real log: the user asked for a document, VEGA ran a web search, the
    verifier caught the mismatch, and the system still reported success and
    recorded the episode as successful - teaching itself to repeat it.
    """
    controller = object.__new__(ASC)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        controller._display_result({
            "success": True, "tier": "autonomous", "outcome_mismatch": True,
            "verification_warning": "asked for a document, did a web search",
            "results": [{"url": "https://example.com"}],
        })
    out = buffer.getvalue().lower()
    assert "successfully" not in out
    assert "what you asked for" in out
    assert "try again" in out


def test_a_real_success_still_reads_as_success():
    controller = object.__new__(ASC)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        controller._display_result({"success": True, "tier": "direct",
                                    "results": [{"message": "Done."}]})
    assert "successfully" in buffer.getvalue().lower()


# --------------------------------------------------------------------------
# 4. File creation: wrong names, empty bodies.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("phrase,expected", [
    ("create a file called shakdown.txt with content hello world", "shakdown.txt"),
    ("create a file named report.txt", "report.txt"),
    ("make a note called groceries", "groceries.txt"),
    ("create a document titled budget 2026", "budget_2026.txt"),
])
def test_filenames_drop_the_introducing_word(phrase, expected):
    """"called shakdown.txt" was literally saved as "called shakdown.txt"."""
    assert ASC._derive_filename(phrase) == expected


def test_filename_never_becomes_the_plan_text():
    """A real session produced To_create_a_structured_document.txt."""
    name = ASC._derive_filename("To create a structured document")
    assert not name.lower().startswith("to_")


@pytest.mark.parametrize("phrase,expected", [
    ("create a file called notes.txt with content hello world", "hello world"),
    ("make list.txt containing buy milk", "buy milk"),
    ("create a file called empty.txt", ""),
])
def test_inline_content_is_recovered(phrase, expected):
    """Files were written 0 bytes when the body sat in the sentence."""
    assert ASC._extract_inline_content(phrase) == expected


# --------------------------------------------------------------------------
# 5. Spoken output read URLs aloud.
# --------------------------------------------------------------------------

def test_urls_and_paths_are_not_read_aloud():
    spoken = ASC._strip_unspeakable(
        "Opened: https://www.google.com/search?q=python+asyncio"
    )
    assert "http" not in spoken
    assert "google.com" not in spoken
    assert "link on screen" in spoken


def test_ordinary_speech_is_untouched():
    text = "Task completed successfully."
    assert ASC._strip_unspeakable(text) == text


# --------------------------------------------------------------------------
# 6. Stale reminders fired on startup.
# --------------------------------------------------------------------------

def test_two_week_old_reminder_is_retired_not_announced(tmp_path):
    """A Test Reminder from 14 days earlier interrupted a fresh session."""
    from core.reminders import ReminderLoop

    path = tmp_path / "schedules.json"
    path.write_text(json.dumps([
        {"id": "stale", "title": "Test Reminder", "status": "pending",
         "reminder_time": (datetime.now() - timedelta(days=14)).isoformat()},
        {"id": "fresh", "title": "Take a break", "status": "pending",
         "reminder_time": (datetime.now() - timedelta(minutes=5)).isoformat()},
    ]), encoding="utf-8")

    fired = [f.get("title") for f in ReminderLoop(path, speak=None).check_once()]
    statuses = {i["id"]: i["status"] for i in json.loads(path.read_text(encoding="utf-8"))}

    assert "Test Reminder" not in fired, "a two-week-old reminder was announced"
    assert statuses["stale"] == "done", "stale reminder left pending to fire again"
    assert "Take a break" in fired, "a genuinely due reminder was suppressed"


# --------------------------------------------------------------------------
# 7. A correct safety refusal looked like a crash.
# --------------------------------------------------------------------------

def test_a_safety_refusal_explains_itself():
    """The Chairman correctly blocked "delete the entire windows folder".

    The rejection set only "reason", while the display reads "error", so the
    user saw "I encountered an issue: Unknown error" - indistinguishable
    from a bug.
    """
    controller = object.__new__(ASC)
    controller._critical_gate_bypass = None

    class RejectingChairman:
        async def validate_plan(self, plan, task):
            return {"approved": False, "reasoning": "irreversible deletion of system files"}

    controller.chairman = RejectingChairman()

    import asyncio
    verdict = asyncio.run(controller._chairman_gate("delete the windows folder", {}))

    assert verdict is not None
    assert verdict["success"] is False
    assert verdict.get("error"), "refusal carried no error message to display"
    assert "unknown error" not in verdict["error"].lower()
    assert "irreversible deletion" in verdict["error"]
