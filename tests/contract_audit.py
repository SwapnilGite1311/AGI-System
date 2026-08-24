"""Contract audit: every intent type PARSED must have an EXECUTION branch."""
import re
from pathlib import Path

src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")

parsed = set(re.findall(r'return \{"type": "([a-z_]+)"', src))
handled = set(re.findall(r'elif intent_type == "([a-z_]+)":', src))
# also if-forms inside _execute_directly
handled |= set(re.findall(r'if intent_type == "([a-z_]+)":', src))

print(f"intent types parsed:  {len(parsed)}")
print(f"types handled:        {len(handled)}")

unhandled = sorted(parsed - handled)
if unhandled:
    print(f"\nUNHANDLED ({len(unhandled)}) - will silently fail or hit generic fallback:")
    for t in unhandled:
        print(f"  - {t}")
else:
    print("\nCONTRACT OK: every parsed intent has an execution branch")

# dead handlers (handled but never parsed) are fine (council-planned actions)
extra = sorted(handled - parsed)
print(f"\nhandled-but-not-parsed (ok - reachable via plans): {len(extra)}")
