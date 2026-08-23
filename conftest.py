"""
Pytest conftest for the E2E command suite (Bon, task #13).

pytest only honors pytest_sessionfinish from plugins/conftest, NOT from test
modules — so the report writer lives here and reads the results list that
tests/test_e2e_commands.py accumulates in its module-level _REPORT list.
"""

from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parent
REPORT_PATH = PROJECT_ROOT / "data" / "e2e_command_report.json"


def pytest_sessionfinish(session, exitstatus):
    # The test module is loaded by pytest under its own name (no tests/ package
    # __init__), so import it from sys.modules rather than by package path.
    import sys
    module = sys.modules.get("test_e2e_commands") or sys.modules.get("tests.test_e2e_commands")
    report = getattr(module, "_REPORT", None) if module else None

    if not report:
        return

    matched = sum(1 for r in report if r["observed_success"] == r["expected_success"])
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({
        "total": len(report),
        "matched_expectations": matched,
        "results": report,
    }, indent=2), encoding="utf-8")
