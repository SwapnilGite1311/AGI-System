"""
Multi-step tasks: goals that cannot be satisfied by a single action.

The frozen v1.0 set in tasks.py is almost entirely single-shot, and the
system scores 100% on it - which says nothing about the thing that actually
feels broken. Every task here needs at least two actions where the SECOND
depends on what the first returned. That is precisely what one-shot tier
routing cannot do: it commits to a plan before seeing any result, so it
wrote a report from a web search it never read.

Each task is achievable with the tools that exist - checked against the
registry's 70 actions - so a failure means the orchestration or the model
fell short, not that the capability is absent.

Kept separate from tasks.py so the frozen benchmark stays comparable
across every run already recorded.

VERSION HISTORY
  1.0  6 tasks. First tiers-vs-react comparison: 33.3% vs 50.0%.
  1.1  18 tasks. Six was too small a sample to route on; results from 1.0
       are NOT directly comparable to 1.1.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

MULTISTEP_VERSION = "1.1"


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


def _titles(ctx) -> List[str]:
    return [str(t.get("title", "")).lower()
            for t in _store(ctx, "business_tasks.json", "tasks")]


def _has_figure(text: str) -> bool:
    return bool(re.search(r"\d", text or ""))


MULTISTEP: List[Dict[str, Any]] = []


def task(**kwargs):
    def register(fn):
        MULTISTEP.append({**kwargs, "verify": fn})
        return fn
    return register


# ---------------------------------------------------------------------------
# measure -> record   (the observation must reach the file)
# ---------------------------------------------------------------------------

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
    if not _has_figure(text):
        return False, f"file holds no figures: {text[:60]!r}"
    return True, ""


@task(id="M3", steps=2,
      command="find out what my CPU usage is and write a short summary to cpu_summary.txt",
      intent="measure, THEN record the measurement")
def _m3(result, output, ctx):
    hit = _find(ctx, "cpu_summary.txt")
    if not hit:
        return False, "no cpu_summary.txt produced"
    if not _has_figure(hit.read_text(encoding="utf-8", errors="replace")):
        return False, "summary contains no measured figure"
    return True, ""


@task(id="M7", steps=2,
      command="count how many tasks I have and save that number to task_count.txt",
      intent="count, THEN write the count that was found")
def _m7(result, output, ctx):
    hit = _find(ctx, "task_count.txt")
    if not hit:
        return False, "no task_count.txt produced"
    if not _has_figure(hit.read_text(encoding="utf-8", errors="replace")):
        return False, "file holds no number"
    return True, ""


# ---------------------------------------------------------------------------
# write -> read back   (confirmation must actually happen)
# ---------------------------------------------------------------------------

@task(id="M2", steps=2,
      command="create a task called integration probe then list the tasks to confirm it exists",
      intent="write a record, THEN read it back")
def _m2(result, output, ctx):
    if not any("integration probe" in t for t in _titles(ctx)):
        return False, "task was never created"
    if "integration probe" not in output.lower():
        return False, "created it but never read it back, so it was not confirmed"
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


@task(id="M8", steps=2,
      command="create a task called followup call and then mark it as done",
      intent="create a record, THEN modify the record just created")
def _m8(result, output, ctx):
    for entry in _store(ctx, "business_tasks.json", "tasks"):
        if "followup call" in str(entry.get("title", "")).lower():
            if str(entry.get("status", "")).lower() == "completed":
                return True, ""
            return False, f"created but still {entry.get('status')!r}"
    return False, "task was never created"


@task(id="M9", steps=2,
      command="create a folder called probe_dir and then list the files to confirm it is there",
      intent="create, THEN verify by listing")
def _m9(result, output, ctx):
    for root in (ctx["data_dir"], ctx["project_root"], Path.home() / "Documents", Path.cwd()):
        try:
            if any(p.is_dir() for p in root.glob("**/probe_dir")):
                return True, ""
        except Exception:
            continue
    return False, "probe_dir was never created"


@task(id="M10", steps=2,
      command="add two team members, first omar then lena, and list the team afterwards",
      intent="two writes THEN a read - the loop must not stop after the first")
def _m10(result, output, ctx):
    names = " ".join(str(x.get("name", "")).lower() for x in _store(ctx, "team_members.json"))
    missing = [n for n in ("omar", "lena") if n not in names]
    if missing:
        return False, f"never added: {', '.join(missing)}"
    return True, ""


# ---------------------------------------------------------------------------
# read -> reason about what was read
# ---------------------------------------------------------------------------

@task(id="M6", steps=2,
      command="how many tasks do I have and does that seem like a lot",
      intent="count first, THEN comment on the number it actually found")
def _m6(result, output, ctx):
    if not _has_figure(output):
        return False, "no count produced"
    return True, ""


@task(id="M11", steps=2,
      command="check my system status and tell me whether memory looks healthy",
      intent="measure, THEN judge the measurement")
def _m11(result, output, ctx):
    if not _has_figure(output):
        return False, "no measurement taken"
    judged = any(word in output.lower() for word in
                 ("healthy", "high", "low", "fine", "ok", "concern", "plenty",
                  "tight", "normal", "usage", "%"))
    if not judged:
        return False, "measured but offered no assessment"
    return True, ""


@task(id="M12", steps=2,
      command="look at my drives and tell me which one has the most free space",
      intent="read all drives, THEN compare them")
def _m12(result, output, ctx):
    if not re.search(r"[A-Za-z]:", output):
        return False, "no drive examined"
    if not _has_figure(output):
        return False, "no free-space figures"
    return True, ""


# ---------------------------------------------------------------------------
# search -> act on what was found
# ---------------------------------------------------------------------------

@task(id="M13", steps=2,
      command="search my files for anything called chain_a and tell me if you found it",
      intent="search, THEN report the actual outcome rather than assuming")
def _m13(result, output, ctx):
    if "chain_a" not in output.lower():
        return False, "never searched for it, or never reported"
    return True, ""


@task(id="M14", steps=2,
      command="take a screenshot and then tell me it was saved",
      intent="act, THEN confirm from the result")
def _m14(result, output, ctx):
    low = output.lower()
    if "screenshot" not in low:
        return False, "no screenshot step"
    if not any(w in low for w in ("captured", "saved", "taken", ".png", "screenshot")):
        return False, "no confirmation of the capture"
    return True, ""


# ---------------------------------------------------------------------------
# documents built from gathered material
# ---------------------------------------------------------------------------

@task(id="M15", steps=3,
      command="find out how many team members there are and write it into a document called team_size",
      intent="count, THEN write a document containing that count")
def _m15(result, output, ctx):
    hit = _find(ctx, "team_size*.docx", "team_size*.txt", "*team_size*")
    if not hit:
        return False, "no team_size document produced"
    if hit.stat().st_size == 0:
        return False, "document is empty"
    return True, ""


@task(id="M16", steps=2,
      command="make a spreadsheet of my tasks and tell me how many rows it has",
      intent="produce a file, THEN report a fact about the file produced")
def _m16(result, output, ctx):
    hit = _find(ctx, "*task*.xlsx", "*.xlsx")
    if not hit:
        return False, "no spreadsheet produced"
    if not _has_figure(output):
        return False, "produced it but never reported the row count"
    return True, ""


# ---------------------------------------------------------------------------
# recovery - the first step fails, a good agent adapts
# ---------------------------------------------------------------------------

@task(id="M17", steps=2,
      command="open the file definitely_not_here_9x7.txt and if that fails create it instead",
      intent="try, observe the failure, THEN take the alternative")
def _m17(result, output, ctx):
    hit = _find(ctx, "definitely_not_here_9x7.txt")
    if not hit:
        return False, "did not fall back to creating the file"
    return True, ""


@task(id="M18", steps=2,
      command="mark the task called no_such_task_here as done and tell me if it was not found",
      intent="attempt, observe it is absent, THEN say so rather than claiming success")
def _m18(result, output, ctx):
    low = output.lower()
    if any(w in low for w in ("not found", "no such", "could not find", "does not exist",
                              "no open task", "no task")):
        return True, ""
    if result.get("success") and "completed" in low:
        return False, "claimed to complete a task that does not exist"
    return True, ""


CATEGORIES = ["multistep"]
TOTAL = len(MULTISTEP)
