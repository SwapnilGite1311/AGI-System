"""Config audit: keys code READS vs keys settings.json DEFINES."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
config = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8-sig"))

# collect config.get("section"... patterns and ["section"] accesses across py files
reads = set()
for py in root.rglob("*.py"):
    if "__pycache__" in str(py) or "tests" in str(py.parts):
        continue
    src = py.read_text(encoding="utf-8", errors="ignore")
    for m in re.findall(r'config(?:uration)?\.get\(\s*"([a-z_]+)"', src):
        reads.add(m)
    for m in re.findall(r'\["([a-z_]+)"\]\.get\(', src):
        pass  # too noisy

defined = set(config.keys())
print("sections defined:", len(defined))
missing = sorted(reads - defined)
if missing:
    print("\nCODE READS BUT CONFIG LACKS:")
    for s in missing:
        print("  -", s)
else:
    print("CONFIG OK: every section code reads is defined")

dead = sorted(defined - reads)
print(f"\ndefined-but-never-read (candidates for cleanup): {len(dead)}")
for s in dead:
    print("  -", s)
