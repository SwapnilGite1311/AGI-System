"""Find success claims that nothing verified.

The recurring failure in this system is not a crash. It is a confident
`{"success": True}` returned for something that did not happen: a form
filled on a page that never loaded, a file "created" that is not on disk,
an email "sent" that went nowhere. Those are worse than errors, because
the user only discovers them by checking by hand.

This walks the AST of every module and flags functions that

  1. perform a side effect - write a file, launch a process, call out over
     the network, mutate stored state, drive the browser - AND
  2. return success=True on a path where nothing checked that it worked.

"Checked" means one of: the side effect's own return value is tested, an
existence/read-back check happens afterwards, or the return is inside a
try whose except returns failure. The last one is weaker than it looks -
a call that fails silently rather than raising slips straight through -
so those are reported separately rather than treated as verified.

Heuristics, not proof. Every finding is a place a human should look, and
the point is that the list is short enough to actually look at.

Run:  python tests/honesty_audit.py [--all] [--json]
"""

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent

# Modules worth auditing: the ones whose success claims reach the user.
TARGET_DIRS = ("agents", "core", "learning")
TARGET_FILES = ("main.py",)

SKIP_NAMES = {"__pycache__", "node_modules", ".git", "venv", ".venv"}


# --------------------------------------------------------------------------
# What counts as a side effect
# --------------------------------------------------------------------------

# Method/function names that change something outside the process.
SIDE_EFFECT_CALLS = {
    # filesystem
    "write_text", "write_bytes", "writelines", "write", "mkdir", "unlink",
    "rmtree", "rename", "replace", "touch", "copy", "copy2", "copyfile",
    "move", "write_json_atomic", "dump", "save",
    # process / system
    "Popen", "run", "call", "check_call", "check_output", "startfile",
    "system", "kill", "terminate", "open_application",
    # network
    "post", "put", "patch", "delete", "request", "urlopen", "send",
    "sendmail", "send_message",
    # browser
    "goto", "click", "fill", "type", "press", "select_option", "screenshot",
    "evaluate", "eval_on_selector",
    # storage
    "execute", "executemany", "commit",
}

# Names that indicate the code checked whether something worked.
VERIFICATION_MARKERS = {
    "exists", "is_file", "is_dir", "stat", "st_size", "getsize",
    "read_text", "read_bytes", "read", "load", "get_text", "inner_text",
    "text_content", "is_visible", "wait_for_selector", "fetchone", "fetchall",
    "status_code", "ok", "returncode", "poll",
}

# Attributes whose truthiness is a check on a prior result.
RESULT_KEYS = {"success", "ok", "status", "result", "returncode", "status_code"}


class FunctionReport:
    def __init__(self, module: str, name: str, lineno: int):
        self.module = module
        self.name = name
        self.lineno = lineno
        self.side_effects: List[str] = []
        self.verifications: List[str] = []
        self.bare_success_lines: List[int] = []
        self.guarded_by_try = False

    @property
    def verified(self) -> bool:
        return bool(self.verifications)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "function": self.name,
            "line": self.lineno,
            "side_effects": sorted(set(self.side_effects)),
            "verifications": sorted(set(self.verifications)),
            "success_lines": self.bare_success_lines,
            "only_try_guarded": self.guarded_by_try and not self.verified,
        }


def _call_name(node: ast.AST) -> Optional[str]:
    """The bare name of whatever is being called."""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            return func.attr
        if isinstance(func, ast.Name):
            return func.id
    return None


def _returns_success_true(node: ast.Return) -> bool:
    """Is this `return {... "success": True ...}`?"""
    value = node.value
    if not isinstance(value, ast.Dict):
        return False
    for key, val in zip(value.keys, value.values):
        if (isinstance(key, ast.Constant) and key.value == "success"
                and isinstance(val, ast.Constant) and val.value is True):
            return True
    return False


def _mentions_verification(node: ast.AST) -> List[str]:
    """Verification-looking names used anywhere under this node."""
    found = []
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr in VERIFICATION_MARKERS:
            found.append(child.attr)
        elif isinstance(child, ast.Call):
            name = _call_name(child)
            if name in VERIFICATION_MARKERS:
                found.append(name)
        # `if result.get("success")` / `if not res["success"]`
        elif isinstance(child, ast.Call) and _call_name(child) == "get":
            for arg in child.args:
                if isinstance(arg, ast.Constant) and arg.value in RESULT_KEYS:
                    found.append(f"get({arg.value!r})")
    return found


def _checked_result_keys(node: ast.AST) -> List[str]:
    """Places where a prior call's result dict is actually tested."""
    found = []
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.Assert, ast.While)):
            for sub in ast.walk(child.test if hasattr(child, "test") else child):
                if isinstance(sub, ast.Call) and _call_name(sub) == "get":
                    for arg in sub.args:
                        if isinstance(arg, ast.Constant) and arg.value in RESULT_KEYS:
                            found.append(f'checks .get("{arg.value}")')
                elif isinstance(sub, ast.Subscript):
                    idx = sub.slice
                    if isinstance(idx, ast.Constant) and idx.value in RESULT_KEYS:
                        found.append(f'checks ["{idx.value}"]')
                elif isinstance(sub, ast.Attribute) and sub.attr in VERIFICATION_MARKERS:
                    found.append(f"checks .{sub.attr}")
    return found


def audit_function(module: str, fn: ast.AST) -> Optional[FunctionReport]:
    report = FunctionReport(module, fn.name, fn.lineno)

    for node in ast.walk(fn):
        name = _call_name(node)
        if name in SIDE_EFFECT_CALLS:
            report.side_effects.append(name)
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                for sub in ast.walk(handler):
                    if isinstance(sub, ast.Return) and not _returns_success_true(sub):
                        report.guarded_by_try = True

    if not report.side_effects:
        return None

    report.verifications.extend(_mentions_verification(fn))
    report.verifications.extend(_checked_result_keys(fn))

    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and _returns_success_true(node):
            report.bare_success_lines.append(node.lineno)

    if not report.bare_success_lines:
        return None
    return report


def audit_module(path: Path) -> List[FunctionReport]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        print(f"  !! could not parse {path}: {exc}")
        return []

    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    reports = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found = audit_function(rel, node)
            if found:
                reports.append(found)
    return reports


def collect_paths() -> List[Path]:
    paths = []
    for directory in TARGET_DIRS:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in SKIP_NAMES for part in path.parts):
                continue
            paths.append(path)
    for filename in TARGET_FILES:
        candidate = ROOT / filename
        if candidate.exists():
            paths.append(candidate)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true",
                        help="include functions that DO verify, for review")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    all_reports: List[FunctionReport] = []
    for path in collect_paths():
        all_reports.extend(audit_module(path))

    unverified = [r for r in all_reports if not r.verified]
    try_only = [r for r in all_reports if r.guarded_by_try and not r.verified]
    verified = [r for r in all_reports if r.verified]

    if args.json:
        print(json.dumps({
            "total_side_effecting_success_returns": len(all_reports),
            "unverified": [r.to_dict() for r in unverified],
            "verified": [r.to_dict() for r in verified] if args.all else [],
        }, indent=2))
        return 0

    print("=" * 78)
    print("HONESTY AUDIT - success claims with nothing behind them")
    print("=" * 78)
    print(f"  functions that act AND report success : {len(all_reports)}")
    print(f"  of those, nothing verifies the action : {len(unverified)}")
    print(f"  (of those, only a try/except guards)  : {len(try_only)}")
    print(f"  verify in some form                   : {len(verified)}")

    if unverified:
        print("\n" + "-" * 78)
        print("REPORTS SUCCESS WITHOUT CHECKING (review these)")
        print("-" * 78)
        by_module: Dict[str, List[FunctionReport]] = {}
        for report in unverified:
            by_module.setdefault(report.module, []).append(report)
        for module in sorted(by_module):
            print(f"\n  {module}")
            for report in sorted(by_module[module], key=lambda r: r.lineno):
                effects = ", ".join(sorted(set(report.side_effects))[:4])
                guard = "  [try/except only]" if report.guarded_by_try else ""
                print(f"     line {report.lineno:5}  {report.name}{guard}")
                print(f"                   does: {effects}")
                print(f"                   says success at line(s): "
                      f"{report.bare_success_lines}")

    if args.all and verified:
        print("\n" + "-" * 78)
        print("VERIFIES (no action needed, listed for review)")
        print("-" * 78)
        for report in sorted(verified, key=lambda r: (r.module, r.lineno)):
            checks = ", ".join(sorted(set(report.verifications))[:3])
            print(f"  {report.module}:{report.lineno} {report.name}  <- {checks}")

    print()
    if unverified:
        print(f"HONESTY AUDIT: {len(unverified)} unverified success claims to review")
    else:
        print("HONESTY AUDIT: every acting function verifies before claiming success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
