"""Structured commands must not be hijacked by the generic browser branch.

_parse_direct_command is an ordered chain, and the browser/search branches
sat ~350 lines above the enterprise ones. Anything containing a
domain-shaped token or the word "search" was claimed by the browser first,
which is why the live shakedown produced:

    "create tenant Acme with domain acme.com"  -> opened acme.com
    "search for files named report"            -> googled it
    "create a document about machine learning" -> googled it
    "create a task named call supplier"        -> googled it

None of these needed a better model; they needed to be matched before the
catch-all.
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


@pytest.mark.parametrize("command,expected_type", [
    ("create a document about machine learning", "create_document"),
    ("write a report on quarterly sales", "create_document"),
    ("create tenant Acme with domain acme.com", "create_tenant"),
    ("search for files named report", "search_files"),
    ("create a task named call supplier", "create_task"),
])
def test_structured_commands_beat_the_browser_catch(controller, command, expected_type):
    intent = controller._parse_direct_command(command)
    assert intent is not None, f"{command!r} found no direct branch at all"
    assert intent["type"] == expected_type, (
        f"{command!r} routed to {intent['type']} instead of {expected_type}"
    )


def test_a_domain_in_a_tenant_command_is_data_not_a_destination(controller):
    """acme.com was opened in a browser instead of stored as the domain."""
    intent = controller._parse_direct_command("create tenant Acme with domain acme.com")
    assert intent["type"] == "create_tenant"
    assert intent["tenant_name"] == "Acme"
    assert intent["domain"] == "acme.com"


def test_file_search_without_a_location_is_not_a_web_search(controller):
    intent = controller._parse_direct_command("search for files named report")
    assert intent["type"] == "search_files"
    assert intent["query"] == "report"


def test_document_topic_is_captured(controller):
    intent = controller._parse_direct_command("create a document about machine learning")
    assert intent["type"] == "create_document"
    assert "machine learning" in (intent.get("topic") or "")


def test_task_title_is_captured(controller):
    intent = controller._parse_direct_command("create a task named call supplier")
    assert intent["type"] == "create_task"
    assert intent["title"] == "call supplier"


# --------------------------------------------------------------------------
# The narrowing that keeps the new branches from over-reaching.
# --------------------------------------------------------------------------

def test_notes_still_reach_the_autonomy_path(controller):
    """"make a note about X" is handled by autonomy, not the document tool.

    An earlier version of the document pattern included "note" and stole it.
    """
    intent = controller._parse_direct_command("make a note about project ideas")
    assert not (intent and intent.get("type") == "create_document")


def test_search_with_a_location_uses_the_path_aware_branch(controller):
    """"<query> in <path>" must keep splitting the location off correctly."""
    intent = controller._parse_direct_command("search files for roadmap in desktop")
    assert intent["type"] == "search_files"
    assert intent["query"] == "roadmap", "the location leaked into the query"


@pytest.mark.parametrize("command", [
    "search the web for python asyncio",
    "google machine learning tutorials",
    "look up the weather on the internet",
])
def test_genuine_web_searches_still_go_to_the_browser(controller, command):
    """Narrowing must not break actual web search."""
    intent = controller._parse_direct_command(command)
    assert not (intent and intent.get("type") == "search_files"), (
        f"{command!r} was misread as a filesystem search"
    )


def test_multi_step_requests_still_decompose(controller):
    """"research X and write me a report" is genuinely two steps.

    It should NOT be captured by the single-intent document branch.
    """
    intent = controller._parse_direct_command(
        "research quantum computing and write me a report"
    )
    assert intent is None, "a multi-step request was collapsed into one action"


# ---------------------------------------------------------------------------
# Reported live: "instead of searching in the system it is searching files on
# google". The guard only recognised the literal words file/folder/document,
# so naming the MACHINE sent the user to the web to find their own files.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phrase", [
    "search my computer for photos",
    "search my laptop for invoices",
    "look on my drive for backups",
    "where is my resume file",
    "locate the file called contract",
    "do i have a file called taxes",
    "find any file with budget in the name",
])
def test_local_file_searches_never_go_to_the_web(controller, phrase):
    intent = controller._parse_direct_command(phrase)
    assert intent is not None, f"{phrase!r} was not recognised at all"
    assert intent["type"] == "search_files", (
        f"{phrase!r} routed to {intent['type']} - a web search for the user's own files"
    )


@pytest.mark.parametrize("phrase", [
    "search the web for python tutorials",
    "google rust lifetimes",
    "search youtube for jazz",
    "look up the weather online",
    "search amazon for headphones",
])
def test_genuine_web_searches_still_go_to_the_web(controller, phrase):
    """Widening the filesystem branch must not swallow real web searches."""
    intent = controller._parse_direct_command(phrase)
    assert not (intent and intent.get("type") == "search_files"), (
        f"{phrase!r} was captured as a filesystem search"
    )


@pytest.mark.parametrize("phrase,expected", [
    ("search for files named report", "report"),
    ("search my computer for photos", "photos"),
    ("locate the file called contract", "contract"),
    ("find files called invoice", "invoice"),
    ("do i have a file called taxes", "taxes"),
])
def test_the_search_term_excludes_the_scaffolding(controller, phrase, expected):
    """"files named report" as a query matches nothing on disk."""
    intent = controller._parse_direct_command(phrase)
    assert intent["query"] == expected
