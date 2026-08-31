"""
Multi-step tasks: goals that cannot be satisfied by a single action.

The frozen v1.0 set is almost entirely single-shot, and the system scores
100% on it - which says nothing about the thing that actually feels broken.
Every task here needs at least two actions where the SECOND depends on what
the first returned. That is precisely what one-shot tier routing cannot do:
it commits to a plan before seeing any result, so it wrote a report from a
web search it never read.

Kept separate from tasks.py so the frozen benchmark stays comparable across
every run already recorded.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

MULTISTEP_VERSION = "1.0"


def _find(ctx, *names: str) -> Optional[Path]:
    roots = [ctx["data_dir"], ctx["documents_dir"], ctx["project_root"],
             Path.cwd(), Path.home() / "Documents"]
    for root in roots:
        try:
            for name in names:
                for hit in root.glob(f"**/{name}"):
                    if hit.is_file():
                        return hit
        except Exception:
            continue
    return None


def _store(ctx, filename: str, key: str = "") -> List[dict]:
    path = ctx["data_dir"] / filename
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = raw.get(key, []) if (key and isinstance(raw, dict)) else raw
    return items if isinstance(items, list) else []


MULTISTEP: List[Dict[str, Any]] = []


def task(**kwargs):
    def register(fn):
        MULTISTEP.append({**kwargs, "verify": fn})
        return fn
    return register


@task(id="M1", steps=2,
      command="check how much disk space is free and save it to a file called disk_report.txt",
      intent="read the drives, THEN write what was read into a file")
def _m1(result, output, ctx):
    hit = _find(ctx, "disk_report.txt")
    if not hit:
        return False, "no disk_report.txt produced"
    text = hit.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return False, "file created but empty - the observation was never used"
    if not re.search(r"\d", text):
        return False, f"file holds no figures: {text[:60]!r}"
    return True, ""


@task(id="M2", steps=2,
      command="create a task called integration probe then list the tasks to confirm it exists",
      intent="write a record, THEN read it back")
def _m2(result, output, ctx):
    titles = [str(t.get("title", "")).lower()
              for t in _store(ctx, "business_tasks.json", "tasks")]
    if not any("integration probe" in t for t in titles):
        return False, "task was never created"
    if "integration probe" not in output.lower():
        return False, "created it but never read it back, so it was not confirmed"
    return True, ""


@task(id="M3", steps=2,
      command="find out what my CPU usage is and write a short summary to cpu_summary.txt",
      intent="measure, THEN record the measurement")
def _m3(result, output, ctx):
    hit = _find(ctx, "cpu_summary.txt")
    if not hit:
        return False, "no cpu_summary.txt produced"
    text = hit.read_text(encoding="utf-8", errors="replace")
    if not re.search(r"\d", text):
        return False, "summary contains no measured figure"
    return True, ""


@task(id="M4", steps=2,
      command="add nadia to the team and then show me the team list",
      intent="write, THEN read back to confirm")
def _m4(result, output, ctx):
    names = [str(x.get("name", "")).lower() for x in _store(ctx, "team_members.json")]
    if not any("nadia" in n for n in names):
        return False, "nadia was never added"
    if "nadia" not in output.lower():
        return False, "added but never listed back"
    return True, ""


@task(id="M5", steps=3,
      command="create a file called chain_a.txt with content step one, then search for files named chain_a to confirm it exists",
      intent="create, THEN search, THEN report what the search found")
def _m5(result, output, ctx):
    hit = _find(ctx, "chain_a.txt")
    if not hit:
        return False, "chain_a.txt was never created"
    if "chain_a" not in output.lower():
        return False, "created but the confirming search never happened"
    return True, ""


@task(id="M6", steps=2,
      command="how many tasks do I have and does that seem like a lot",
      intent="count first, THEN comment on the number it actually found")
def _m6(result, output, ctx):
    if not re.search(r"\d", output):
        return False, "no count produced"
    return True, ""


CATEGORIES = ["multistep"]
TOTAL = len(MULTISTEP)
