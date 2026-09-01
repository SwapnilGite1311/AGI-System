"""Chairman safety-gate tests.

core/chairman.py is the last check before a destructive command runs, and it
sat at 26% coverage - the lowest of any safety-relevant module. Nothing
verified that a rejection actually rejects, that malformed model output is
caught rather than executed, or that a model outage fails closed.

These use a stubbed generator rather than a live model, so they assert the
gate's own logic and run without Ollama.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.chairman import Chairman  # noqa: E402


CONFIG = str(Path(__file__).resolve().parents[1] / "config" / "settings.json")


def build_chairman(reply=None, raises=None):
    """A Chairman whose model layer is replaced by a canned reply."""
    chairman = object.__new__(Chairman)
    chairman.model = "stub-model"

    async def fake_generate(prompt, num_predict=None, **kwargs):
        if raises:
            raise raises
        return {"response": reply}, "stub-model"

    chairman._generate_with_fallbacks = fake_generate
    return chairman


DESTRUCTIVE_PLAN = {"steps": [{"action": "delete_folder", "path": "C:/Users/x/Documents"}]}


# --------------------------------------------------------------------------
# _parse_response - the seam where malformed output used to slip through
# --------------------------------------------------------------------------

def test_parse_response_reads_plain_json():
    chairman = build_chairman()
    parsed = chairman._parse_response('{"approved": true, "reasoning": "fine"}')
    assert parsed["approved"] is True
    assert "error" not in parsed


def test_parse_response_strips_markdown_fences():
    chairman = build_chairman()
    parsed = chairman._parse_response('```json\n{"approved": false}\n```')
    assert parsed["approved"] is False
    assert "error" not in parsed


def test_parse_response_extracts_json_surrounded_by_prose():
    """Small models prepend explanations; the verdict must still be read."""
    chairman = build_chairman()
    parsed = chairman._parse_response(
        'Sure! Here is my review:\n{"approved": true, "confidence": 0.9}\nHope that helps.'
    )
    assert parsed["approved"] is True
    assert parsed["confidence"] == 0.9


def test_parse_response_flags_unparseable_output_as_an_error():
    """Must set "error", not only "parse_error".

    Callers detect failure with `if "error" in result`. When only
    "parse_error" was set, unreadable model output was treated as a valid
    empty verdict and the command proceeded.
    """
    chairman = build_chairman()
    parsed = chairman._parse_response("I'm not sure what you want me to do here.")
    assert "error" in parsed, "unparseable output was not flagged as an error"
    assert parsed.get("raw_response")


# --------------------------------------------------------------------------
# validate_plan - the gate itself
# --------------------------------------------------------------------------

def test_validate_plan_passes_an_approval_through():
    chairman = build_chairman(
        reply=json.dumps({"approved": True, "final_verdict": "approve",
                          "reasoning": "creates a file the user asked for"})
    )
    result = asyncio.run(chairman.validate_plan({"steps": []}, "create notes.txt"))
    assert result["approved"] is True
    assert result["authority"] == "chairman"


def test_validate_plan_honours_a_rejection():
    chairman = build_chairman(
        reply=json.dumps({"approved": False, "final_verdict": "reject",
                          "reasoning": "irreversible deletion of user data"})
    )
    result = asyncio.run(chairman.validate_plan(DESTRUCTIVE_PLAN, "delete my documents"))
    assert result["approved"] is False
    assert "deletion" in result["reasoning"].lower()


def test_validate_plan_defaults_to_not_approved_when_the_verdict_omits_it():
    """Absence of approval is not approval."""
    chairman = build_chairman(reply=json.dumps({"reasoning": "hmm", "confidence": 0.4}))
    result = asyncio.run(chairman.validate_plan(DESTRUCTIVE_PLAN, "delete everything"))
    assert result["approved"] is False, "a verdict with no 'approved' key was treated as approval"


def test_validate_plan_does_not_approve_on_unparseable_output():
    """Garbage from the model must never read as consent."""
    chairman = build_chairman(reply="uhh I think that's probably fine? maybe")
    result = asyncio.run(chairman.validate_plan(DESTRUCTIVE_PLAN, "format the disk"))
    assert result["approved"] is False
    assert "error" in result


def test_validate_plan_fails_closed_when_the_model_is_unavailable():
    """A model outage must not become an approval."""
    chairman = build_chairman(raises=RuntimeError("ollama connection refused"))
    result = asyncio.run(chairman.validate_plan(DESTRUCTIVE_PLAN, "delete my documents"))
    assert result["approved"] is False
    assert result["final_verdict"] == "reject"
    assert "ollama connection refused" in result["reasoning"]


@pytest.mark.parametrize("refusal", ["false", "no", "reject", "maybe", False, 0, 1, None, {"x": 1}])
def test_a_quoted_refusal_is_never_read_as_approval(refusal):
    """The string "false" must not approve a destructive plan.

    Small local models routinely emit quoted booleans. `"approved": "false"`
    is a non-empty string, which is truthy in Python - and main.py's gate
    reads it as `if validation.get("approved"):`. That approved destructive
    plans the Chairman had explicitly rejected. Everything ambiguous now
    fails closed.
    """
    chairman = build_chairman(reply=json.dumps({"approved": refusal}))
    result = asyncio.run(chairman.validate_plan(DESTRUCTIVE_PLAN, "delete everything"))
    assert result["approved"] is False, f"{refusal!r} was treated as approval"


@pytest.mark.parametrize("consent", ["true", "TRUE", "yes", "approve", True])
def test_a_genuine_approval_still_passes(consent):
    """Failing closed must not break the normal approve path."""
    chairman = build_chairman(reply=json.dumps({"approved": consent}))
    result = asyncio.run(chairman.validate_plan({"steps": []}, "create a file"))
    assert result["approved"] is True


def test_approval_is_always_a_real_boolean():
    """Callers rely on truthiness; the type must never be a surprise."""
    chairman = build_chairman(reply=json.dumps({"approved": "true"}))
    result = asyncio.run(chairman.validate_plan({"steps": []}, "create a file"))
    assert isinstance(result["approved"], bool)


# --------------------------------------------------------------------------
# emergency fallback
# --------------------------------------------------------------------------

def test_emergency_fallback_picks_the_most_confident_opinion():
    chairman = build_chairman()
    opinions = [
        {"member": "speed", "confidence": 0.3, "plan": "a"},
        {"member": "strategist", "confidence": 0.9, "plan": "b"},
        {"member": "analyst", "confidence": 0.6, "plan": "c"},
    ]
    result = chairman._emergency_fallback(opinions)
    assert result["chosen"]["member"] == "strategist"
    assert result["resolution_type"] == "emergency_fallback"
    assert result.get("warning"), "a fallback decision must be labelled as one"


def test_emergency_fallback_handles_missing_confidence():
    chairman = build_chairman()
    result = chairman._emergency_fallback([{"member": "a"}, {"member": "b", "confidence": 0.5}])
    assert result["chosen"]["member"] == "b"
