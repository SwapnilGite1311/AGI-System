"""Commands the recorded live session got wrong.

Extracted from logs.txt - every case below is something the user actually
typed and did not get. The session shows the same request asked four
different ways and failing each time: "why failed it is such a simple task
can't you just open the spreadsheet?"
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import AutonomousSystemController as ASC  # noqa: E402

CONFIG = Path(__file__).resolve().parents[1] / "config" / "settings.json"


@pytest.fixture
def controller():
    c = object.__new__(ASC)
    c.config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    return c


# --------------------------------------------------------------------------
# Opening a file. Asked four ways in the session; none worked.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("phrase", [
    "open my_tasks.xlsx",
    "just open my_tasks.xlsx from documents folder",
    "my_tasks.xlsx",
    "open the file report.pdf",
    "please open budget.xlsx from desktop",
])
def test_opening_a_named_file_is_recognised(controller, phrase):
    intent = controller._parse_direct_command(phrase)
    assert intent is not None, f"{phrase!r} fell through to the model"
    assert intent["type"] == "open_file"
    assert intent["filename"].endswith((".xlsx", ".pdf"))


def test_the_folder_is_captured_when_given(controller):
    intent = controller._parse_direct_command(
        "just open my_tasks.xlsx from documents folder")
    assert intent["where"] and "document" in intent["where"].lower()


# --------------------------------------------------------------------------
# Deleting a named file - previously reached the model, which searched.
# --------------------------------------------------------------------------

def test_deleting_a_named_file_is_recognised(controller):
    intent = controller._parse_direct_command(
        "delete the spreadsheet my_tasks.xlsx in documents folder")
    assert intent["type"] == "delete_named_file"
    assert intent["filename"] == "my_tasks.xlsx"


# --------------------------------------------------------------------------
# Questions about itself. A 3B model cannot know which model it is or where
# it lives, so it invented answers; these facts are read from config.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("phrase,topic", [
    ("so tell me which model are you using currently?", "model"),
    ("which model exactly like llama, tinyllama which one exactly?", "model"),
    ("so in which folder are you situated?", "location"),
    ("where are your files", "location"),
    ("Tell me what you can do.", "capabilities"),
    ("what can you do", "capabilities"),
])
def test_self_questions_are_answered_from_fact(controller, phrase, topic):
    intent = controller._parse_direct_command(phrase)
    assert intent is not None, f"{phrase!r} fell through to the model"
    assert intent["type"] == "self_report"
    assert intent["topic"] == topic


def test_self_report_returns_the_real_configuration(controller):
    controller.tool_registry = controller._build_tool_registry()

    models = controller._describe_self("model")
    assert models["success"]
    assert models["models_by_role"], "no models reported"

    location = controller._describe_self("location")
    assert Path(location["project_root"]).exists()

    capabilities = controller._describe_self("capabilities")
    assert len(capabilities["capabilities"]) >= 5


# --------------------------------------------------------------------------
# Whisper annotations were executed as commands.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("noise", [
    "[Typewriter sounds]",
    "(keyboard clicking) (keyboard clicking)",
    "[BLANK_AUDIO]",
    "[silence]",
])
def test_transcription_noise_is_not_executed(controller, noise):
    intent = controller._parse_direct_command(noise)
    assert intent is not None
    assert intent["type"] == "transcription_noise"


@pytest.mark.parametrize("real", [
    "list tasks",
    "system info",
    "open notepad",
])
def test_real_commands_are_not_mistaken_for_noise(controller, real):
    assert not ASC._is_transcription_noise(real)


# --------------------------------------------------------------------------
# Team member with contact details.
# --------------------------------------------------------------------------

def test_team_member_with_an_email(controller):
    intent = controller._parse_direct_command(
        "add priya to team with email priyajadha12@gmail.com")
    assert intent["type"] == "add_team_member"
    assert intent["name"].lower() == "priya"
    assert intent["email"] == "priyajadha12@gmail.com"


# --------------------------------------------------------------------------
# The new branches must not shadow existing ones. Every one of these broke
# when the bare-filename pattern allowed spaces, so "create a file named
# report.txt" was read as a single filename to open.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("phrase,expected", [
    ("create a file named report.txt", "create_file"),
    ("get file info for notes.txt", "file_info"),
    ("search for files named report", "search_files"),
    ("list tasks", "list_tasks"),
    ("take a screenshot", "screenshot"),
])
def test_existing_routing_is_not_shadowed(controller, phrase, expected):
    intent = controller._parse_direct_command(phrase)
    assert intent is not None and intent["type"] == expected
