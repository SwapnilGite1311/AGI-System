"""Intent detection matrix test (#10b).

Auto-extracts every phrase->intent mapping from main.py source and verifies
that _parse_direct_command() maps each representative phrase to the expected
intent type. Detection-only: no actions are executed.
"""

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as asc_module  # noqa: E402

SOURCE = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

PAIR_RE = re.compile(
    r'if any\(phrase in normalized for phrase in \[(?P<phrases>[^\]]+)\]\):\s*\n\s*return \{"type": "(?P<intent>[a-z_]+)"'
)
PHRASE_RE = re.compile(r'"([^"]+)"')


def extract_pairs():
    pairs = []
    for match in PAIR_RE.finditer(SOURCE):
        phrases = PHRASE_RE.findall(match.group("phrases"))
        if phrases:
            pairs.append((phrases[0], match.group("intent")))
    return pairs


def main():
    controller = object.__new__(asc_module.AutonomousSystemController)
    config_path = Path(__file__).resolve().parents[1] / "config" / "settings.json"
    import json

    controller.config = json.loads(config_path.read_text(encoding="utf-8"))
    pairs = extract_pairs()
    print(f"extracted phrase->intent mappings from source: {len(pairs)}")

    failures = []
    for phrase, expected in pairs:
        try:
            result = controller._parse_direct_command(phrase)
        except Exception as exc:  # noqa: BLE001
            failures.append((phrase, expected, f"EXCEPTION {type(exc).__name__}: {exc}"))
            continue
        got = (result or {}).get("type")
        if got != expected:
            failures.append((phrase, expected, f"got {got!r}"))

    passed = len(pairs) - len(failures)
    print(f"\nPASS: {passed}/{len(pairs)}")

    if failures:
        print("\nFAILURES:")
        for phrase, expected, detail in failures:
            print(f"  {phrase!r:45} expected={expected:25} {detail}")
        sys.exit(1)
    print("INTENT MATRIX: ALL PASS")


if __name__ == "__main__":
    main()
