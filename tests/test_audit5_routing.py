"""Routing gaps found in the final pre-MVP audit.

A probe of twenty phrasings a person would actually type found half had no
deterministic branch. Five of those failed outright when the model handled
them - including one that reported success for work it never did.
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


@pytest.mark.parametrize("phrase,expected", [
    # Was answered by the conversation tier with "Sure thing, Priya added."
    # while adding nobody - a claim about work that never happened.
    ("add priya to the team", "add_team_member"),
    ("register Sam into the team", "add_team_member"),

    # Failed with "Task ID is required to update a task"; a person never
    # has the uuid.
    ("mark call supplier as done", "complete_task"),
    ("set review budget as complete", "complete_task"),

    # Routed to web search and failed with "Search query missing".
    ("read the text on my screen", "extract_text"),
    ("what text is on my screen", "extract_text"),

    # Measured the project folder (54 MB) and reported it as free space.
    ("how much disk do i have left", "disk_drives"),
    ("how much free storage is there", "disk_drives"),

    # Listed the tasks instead of producing a file.
    ("create a spreadsheet of my tasks", "create_spreadsheet"),
    ("export an excel of my tasks", "create_spreadsheet"),
])
def test_everyday_phrasings_route_deterministically(controller, phrase, expected):
    intent = controller._parse_direct_command(phrase)
    assert intent is not None, f"{phrase!r} still falls through to the model"
    assert intent["type"] == expected


def test_the_team_member_name_is_captured(controller):
    intent = controller._parse_direct_command("add priya to the team")
    assert intent["name"].lower() == "priya"


def test_the_task_title_is_captured(controller):
    intent = controller._parse_direct_command("mark call supplier as done")
    assert intent["title"].lower() == "call supplier"


@pytest.mark.parametrize("phrase,expected", [
    ("list tasks", "list_tasks"),
    ("disk drives", "disk_drives"),
    ("take a screenshot", "screenshot"),
    ("create a document about machine learning", "create_document"),
    ("create a file named report.txt", "create_file"),
])
def test_existing_routing_is_unchanged(controller, phrase, expected):
    """The new branches sit ahead of others; nothing may be shadowed."""
    intent = controller._parse_direct_command(phrase)
    assert intent is not None and intent["type"] == expected


@pytest.mark.parametrize("phrase", [
    "how are you today",
    "what do you think about rust",
    "tell me a joke",
])
def test_conversation_is_not_captured_by_the_new_branches(controller, phrase):
    """Widening the parser must not swallow ordinary chat."""
    intent = controller._parse_direct_command(phrase)
    assert intent is None or intent["type"] not in {
        "add_team_member", "complete_task", "extract_text",
        "disk_drives", "create_spreadsheet",
    }


def test_completing_an_ambiguous_task_asks_instead_of_guessing():
    """Two open tasks matching the same words must not be resolved silently."""
    import asyncio

    controller = object.__new__(ASC)

    class Business:
        tasks = [
            {"id": "1", "title": "call supplier about pricing", "status": "pending"},
            {"id": "2", "title": "call supplier about delivery", "status": "pending"},
        ]

        def update_task_status(self, task_id, status):
            raise AssertionError("completed a task without disambiguating")

    controller.agents = {"business": Business()}
    controller._record_action_stats = lambda *a, **k: None

    result = asyncio.run(controller._execute_directly(
        "mark call supplier as done",
        {"intent": {"type": "complete_task", "title": "call supplier"}},
    ))
    assert result["success"] is False
    assert "which one" in json.dumps(result).lower()
