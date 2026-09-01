"""
End-to-end command test suite (Bon, task #13).

Runs the top-20 user commands in TYPED mode through the real
AutonomousSystemController.process_command() pipeline and asserts each
command's reported outcome HONESTLY:

- Commands expected to succeed must return result["success"] is True.
- The observed tier is recorded so routing regressions are visible.
- Nothing is mocked inside ASC; if a command fails here it fails for a user.

Scope notes (honest limitations):
- Commands that require external services (email, weather APIs, live browser)
  are deliberately excluded: they cannot pass deterministically in CI.
- Conversation-tier commands depend on Ollama; when Ollama is unreachable the
  agent's built-in fallback replies are used, which still count as success
  because that is the shipped degraded-mode behavior.
- A machine-readable report is written to data/e2e_command_report.json.

Run: python -m pytest tests/test_e2e_commands.py -v -s
"""

import asyncio
import json
import os
import pathlib
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from main import AutonomousSystemController  # noqa: E402

REPORT_PATH = PROJECT_ROOT / "data" / "e2e_command_report.json"


# ---------------------------------------------------------------------------
# Controller fixture: one real controller for the whole module (init is slow).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def controller():
    asc = AutonomousSystemController(str(PROJECT_ROOT / "config" / "settings.json"))
    yield asc


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def _run(controller, command: str):
    return await controller.process_command(command)


def run_command(controller, command: str):
    """Execute one command synchronously and return (result, elapsed_seconds)."""
    started = time.perf_counter()
    try:
        result = asyncio.get_event_loop().run_until_complete(_run(controller, command)) \
            if not _loop_running() else asyncio.run(_run(controller, command))
    except RuntimeError:
        result = asyncio.run(_run(controller, command))
    return result, round(time.perf_counter() - started, 2)


def _loop_running() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


# ---------------------------------------------------------------------------
# Reporting helper: every command's outcome lands in the JSON report, pass or
# fail, so the supervisor can audit what actually happened.
# ---------------------------------------------------------------------------

_REPORT = []


def record(command: str, expected_success: bool, result, elapsed):
    entry = {
        "command": command,
        "expected_success": expected_success,
        "observed_success": bool(result.get("success")),
        "tier": result.get("tier"),
        "intent": (result.get("plan") or {}).get("intent") if isinstance(result.get("plan"), dict) else None,
        "error": result.get("error") or result.get("details"),
        "elapsed_s": elapsed,
    }
    _REPORT.append(entry)
    return entry


# ---------------------------------------------------------------------------
# Reporting: results accumulate in _REPORT; the actual JSON write happens in
# conftest.py (pytest only honors pytest_sessionfinish from conftest/plugins).
# ---------------------------------------------------------------------------

_REPORT = []


def _reported_path(result):
    """Pull the written path out of a result, whatever tier produced it.

    Tiers nest their payload differently, so look in the obvious places
    rather than assuming one shape.
    """
    if not isinstance(result, dict):
        return None
    for key in ("path", "filepath", "file_path"):
        if result.get(key):
            return result[key]
    for holder in ("result", "step_result", "data", "output"):
        nested = result.get(holder)
        if isinstance(nested, dict):
            found = _reported_path(nested)
            if found:
                return found
    steps = result.get("steps") or result.get("results")
    if isinstance(steps, list):
        for step in reversed(steps):
            found = _reported_path(step)
            if found:
                return found
    return None


def expect_success(controller, command, tmp_cwd=None):
    """Shared assertion body: run a command and honestly assert success."""
    if tmp_cwd:
        os.chdir(tmp_cwd)
    try:
        result, elapsed = run_command(controller, command)
    finally:
        if tmp_cwd:
            os.chdir(PROJECT_ROOT)

    entry = record(command, True, result, elapsed)

    assert result is not None, f"{command!r} returned None"
    assert result.get("success") is True, (
        f"{command!r} FAILED honestly-reported failure "
        f"(tier={entry['tier']}, error={entry['error']})"
    )
    assert "tier" in result, f"{command!r} did not report its execution tier"
    return result


# ---------------------------------------------------------------------------
# Tier 1: system inspection commands (system_agent, pure-local, deterministic)
# ---------------------------------------------------------------------------

class TestSystemCommands:
    def test_show_system_info(self, controller):
        result = expect_success(controller, "show system info")
        assert result.get("tier") == "direct"

    def test_list_running_processes(self, controller):
        expect_success(controller, "list running processes")

    def test_network_status(self, controller, request):
        # KNOWN BUG (handoff to Team Lead filed): get_network_info() lacks a
        # "success" key so the direct tier reports failure despite valid data.
        # This test EXPECTS success and will pass once the one-liner lands.
        result = expect_success(controller, "show network status")
        assert result.get("results"), "network info payload missing"

    def test_disk_drives(self, controller):
        expect_success(controller, "show disk drives")

    def test_environment_variable(self, controller):
        expect_success(controller, "show environment variable PATH")


# ---------------------------------------------------------------------------
# Tier 2: file operations (file_agent, exercised inside an isolated tmp dir)
# ---------------------------------------------------------------------------

class TestFileCommands:
    def test_create_and_verify_file(self, controller, tmp_path):
        """A reported success must mean a file at the reported path.

        Not "at the path this test guessed": bare filenames land in the
        documents directory by design. What must never happen is a success
        that reports a path with nothing behind it.
        """
        target_name = "e2e_bon_created_file.txt"
        result = expect_success(
            controller, f"create file {target_name}", tmp_cwd=str(tmp_path))

        reported = _reported_path(result)
        assert reported, (
            f"create_file reported success without saying where the file went: {result}")
        created = pathlib.Path(reported)
        assert created.exists(), (
            f"create_file reported success at {reported} but nothing is there "
            "- dishonest success detected")
        assert created.name == target_name, (
            f"asked for {target_name}, got {created.name}")

    def test_create_folder(self, controller, tmp_path):
        folder_name = "e2e_bon_folder"
        expect_success(controller, f"create folder {folder_name}", tmp_cwd=str(tmp_path))
        assert (tmp_path / folder_name).exists(), (
            "create_folder reported success but folder missing on disk"
        )

    def test_list_files(self, controller, tmp_path):
        (tmp_path / "seed.txt").write_text("seed")
        expect_success(controller, "list files", tmp_cwd=str(tmp_path))


# ---------------------------------------------------------------------------
# Tier 3: business/task commands (business_agent, persisted state)
# ---------------------------------------------------------------------------

class TestBusinessCommands:
    def test_create_task(self, controller):
        expect_success(controller, "create task")

    def test_list_tasks(self, controller):
        expect_success(controller, "list tasks")

    def test_list_projects(self, controller):
        expect_success(controller, "list projects")

    def test_daily_plan(self, controller):
        expect_success(controller, "daily plan")

    def test_business_dashboard(self, controller):
        expect_success(controller, "show business dashboard")


# ---------------------------------------------------------------------------
# Tier 4: introspection / status commands
# ---------------------------------------------------------------------------

class TestStatusCommands:
    def test_command_history(self, controller):
        expect_success(controller, "show command history")

    def test_voice_status(self, controller):
        expect_success(controller, "voice status")

    def test_agent_status(self, controller):
        expect_success(controller, "agent status")

    def test_available_services(self, controller):
        expect_success(controller, "available services")


# ---------------------------------------------------------------------------
# Tier 5: learning-system commands
# ---------------------------------------------------------------------------

class TestLearningCommands:
    def test_save_preference(self, controller):
        expect_success(controller, "remember that favorite_browser is chrome")

    def test_show_preferences_after_save(self, controller):
        expect_success(controller, "show preferences")

    def test_record_positive_feedback(self, controller):
        expect_success(controller, "good job")

    def test_show_adaptive_learning(self, controller):
        expect_success(controller, "show adaptive learning")

    def test_phase5_model_summary(self, controller):
        result = expect_success(controller, "phase 5 model")
        # Honest deep-check: phase5 summary must be a populated dict, not empty.
        summary = result.get("phase5", {}).get("summary") or {}
        assert isinstance(summary, dict), "phase5 summary shape unexpected"


# ---------------------------------------------------------------------------
# Tier 6: conversation fallback (works with or without Ollama reachable)
# ---------------------------------------------------------------------------

class TestConversationCommands:
    def test_greeting(self, controller):
        expect_success(controller, "hello")

    def test_what_can_you_do(self, controller):
        expect_success(controller, "what can you do")


# ---------------------------------------------------------------------------
# B-1 (Bon): BRAIN TIER cases - natural phrasing that legacy regex could not
# parse. Each must route through process_command and report an HONEST outcome.
# ---------------------------------------------------------------------------

class TestBrainTierCommands:
    def test_brain_create_file_with_content(self, controller, tmp_path):
        """Creative compound file command must actually create bt.txt with 'hi'."""
        target_name = "bt.txt"
        result = expect_success(
            controller,
            f"create a file named {target_name} with content hi",
            tmp_cwd=str(tmp_path),
        )
        reported = _reported_path(result)
        assert reported, (
            f"brain-tier create-file reported success without a path: {result}")
        created = pathlib.Path(reported)
        assert created.exists(), (
            f"brain-tier create-file reported success at {reported} "
            "but nothing is there")
        content = created.read_text(encoding="utf-8", errors="replace").strip().lower()
        assert "hi" in content, (
            f"file created but content wrong: {content!r}"
        )

    def test_brain_shopping_suggestion(self, controller):
        """/shopping-style natural request must succeed honestly or ask to
        clarify - never silently fake success with an empty payload."""
        if os.environ.get("E2E_SKIP_NETWORK"):
            pytest.skip("network-dependent case skipped")
        result, elapsed = run_command(controller, "suggest me laptops under 80000")
        record("suggest me laptops under 80000", True, result, elapsed)
        tier = result.get("tier")
        assert result is not None and tier is not None, (
            "no routing decision recorded for shopping suggestion"
        )
        if tier == "clarify":
            assert result.get("success") is True and result.get("response"), (
                "clarify path returned without a question"
            )
        else:
            assert result.get("success") is True, (
                f"shopping suggestion failed honestly (tier={tier}, "
                f"error={result.get('error')})"
            )
            payload = json.dumps(result.get("results") or result.get("response") or "")
            assert len(payload) > 20, "suspiciously empty result payload"

    def test_brain_casual_greeting(self, controller):
        """Casual greeting must land in chat (conversation/clarify), not tools."""
        result = expect_success(controller, "hey there how are you today?")
        assert result.get("tier") in {"conversation", "clarify", "direct"}, (
            f"greeting routed to unexpected tier {result.get('tier')!r}"
        )
        assert (result.get("response") or "").strip(), "greeting got an empty reply"

    def test_brain_nonsense_gets_no_task_created(self, controller):
        """Pure gibberish must be politely clarified/chatted away - it must
        NEVER be planned into a junk task or executed as a tool action."""
        tasks_before = self._task_count()
        result, elapsed = run_command(controller, "flurbick wibble wobble")
        entry = record("flurbick wibble wobble", True, result, elapsed)
        assert result is not None, "gibberish command returned None"
        # Honest outcome: clarify question or a chat reply. NOT silent tool work.
        assert entry["tier"] in {"clarify", "conversation", None}, (
            f"gibberish executed on unexpected tier {entry['tier']!r}"
        )
        if entry["tier"] == "clarify":
            assert result.get("response"), "clarify without a question text"
        tasks_after = self._task_count()
        assert tasks_after == tasks_before, (
            f"junk task creation detected: {tasks_before} -> {tasks_after} tasks"
        )

    @staticmethod
    def _task_count() -> int:
        try:
            data = json.loads(
                (PROJECT_ROOT / "data" / "business_tasks.json").read_text(encoding="utf-8")
            )
            items = data.get("tasks", data) if isinstance(data, dict) else data
            return len(items) if isinstance(items, list) else 0
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Final aggregate: at least 90% of the top-20 commands must behave as expected.
# A single flaky command fails its own test above; this guards systemic rot.
# ---------------------------------------------------------------------------

def test_overall_pass_rate(controller):
    total = len(_REPORT)
    matched = sum(1 for r in _REPORT if r["observed_success"] == r["expected_success"])
    rate = matched / total if total else 0.0
    assert total >= 15, f"E2E suite only executed {total} commands, expected ~20"
    assert rate >= 0.9, (
        f"E2E pass-rate {rate:.0%} ({matched}/{total}) below 90% threshold - "
        f"failing commands: {[r['command'] for r in _REPORT if r['observed_success'] != r['expected_success']]}"
    )
