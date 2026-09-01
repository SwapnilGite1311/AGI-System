"""Email sending and form filling.

Both were reported broken in the live shakedown:
  "if i said it to send email to this mail regarding project it can't"
  "can it fill out forms then like if i give it a link"
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.web_agent import WebAgent  # noqa: E402
from main import AutonomousSystemController as ASC  # noqa: E402

CONFIG = str(Path(__file__).resolve().parents[1] / "config" / "settings.json")


@pytest.fixture
def controller():
    c = object.__new__(ASC)
    c.config = json.loads(Path(CONFIG).read_text(encoding="utf-8-sig"))
    return c


# --------------------------------------------------------------------------
# Email: there was no send_email branch in the direct parser at all, so every
# email request depended on a 3B model emitting correct JSON, and failed.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("phrase,recipient,subject_contains", [
    ("send an email to john@example.com regarding project",
     "john@example.com", "project"),
    ("send email to john@example.com about the project update",
     "john@example.com", "project update"),
    ("email john@example.com saying the report is ready",
     "john@example.com", "report is ready"),
    ("send a mail to boss@corp.io regarding Q4 numbers",
     "boss@corp.io", "Q4 numbers"),
])
def test_email_requests_are_parsed_deterministically(controller, phrase, recipient, subject_contains):
    intent = controller._parse_direct_command(phrase)
    assert intent is not None, "email request was not recognised at all"
    assert intent["type"] == "send_email"
    assert intent["to_email"] == recipient
    haystack = f"{intent.get('subject') or ''} {intent.get('body') or ''}".lower()
    assert subject_contains.lower() in haystack


def test_email_with_explicit_subject_and_body(controller):
    intent = controller._parse_direct_command(
        "send an email to john@example.com with subject Update and body all done"
    )
    assert intent["to_email"] == "john@example.com"
    assert intent["subject"] == "Update", "trailing conjunction leaked into the subject"
    assert "all done" in intent["body"]


def test_email_without_a_recipient_asks_rather_than_guessing(controller):
    intent = controller._parse_direct_command("send an email regarding project")
    assert intent["type"] == "send_email"
    assert intent["to_email"] is None
    assert intent["needs"] == "recipient"


@pytest.mark.parametrize("phrase", ["check my email", "read my inbox", "any new mail"])
def test_reading_mail_is_not_treated_as_sending(controller, phrase):
    """Only send-shaped phrasings should become send_email."""
    intent = controller._parse_direct_command(phrase)
    assert not (intent and intent.get("type") == "send_email")


# --------------------------------------------------------------------------
# Forms: the URL itself was being parsed as a form field and typed into
# the page.
# --------------------------------------------------------------------------

@pytest.fixture
def web():
    return WebAgent(CONFIG)


def test_the_url_is_never_treated_as_a_form_field(web):
    """"https://example.com/apply" matched the key:value pattern.

    It produced {"fill this form for me https": "//example.com/apply"} and
    that string was then entered into the form as an answer.
    """
    fields = web._extract_inline_fields("fill this form for me https://example.com/apply")
    assert fields == {}, f"URL leaked into form fields: {fields}"


def test_real_field_values_are_still_extracted(web):
    fields = web._extract_inline_fields(
        "go to https://example.com/apply and fill name 'Swapnil' email 'me@x.com'"
    )
    assert fields == {"name": "Swapnil", "email": "me@x.com"}


def test_colon_style_pairs_survive_url_stripping(web):
    fields = web._extract_inline_fields(
        "fill the form at https://example.com/signup with name: Swapnil, email: me@x.com"
    )
    assert fields.get("name") == "Swapnil"
    assert fields.get("email") == "me@x.com"
    assert not any("http" in k for k in fields)


def test_scaffolding_words_are_not_field_names(web):
    fields = web._extract_inline_fields("please go to the form and fill name 'Swapnil'")
    assert set(fields) <= {"name"}, f"stopwords leaked in: {fields}"
