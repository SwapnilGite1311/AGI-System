"""
Bootstrap the semi-supervised layer, and measure whether it helped.

The learning layer only ever saw whatever the user happened to type, so it
had a few hundred examples dominated by a handful of phrasings. This gives
it a broad, correctly-labelled starting corpus - the "train on basics first,
adapt to the user later" idea - without inventing capabilities.

Method, so the result means something:

  * Labels come from the system's OWN deterministic parser, not from me.
    An example is kept only where the parser already routes it correctly,
    so the model learns to generalise from behaviour that is verified
    right, rather than from my guesses about what should happen.

  * Train and evaluate on DISJOINT phrasings. Every intent appears in both
    sets worded differently, so the score measures generalisation to
    unseen wording - the actual weakness - not memorisation.

  * The held-out set is scored before and after fitting. Training that does
    not move that number did not help, whatever the training metrics say.

    python benchmark/train.py --dry-run     # corpus stats only
    python benchmark/train.py               # measure, fit, measure again
"""

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Phrasings grouped by what the user means. Two independent wordings per
# intent: the first list trains, the second is never trained on.
CORPUS: Dict[str, Tuple[List[str], List[str]]] = {
    "system_info": (
        ["system info", "show me system information", "system status",
         "how is my machine doing", "check system health", "machine stats",
         "give me a system report", "what are my system specs"],
        ["how's my computer holding up", "run a health check on this machine",
         "tell me about this pc"],
    ),
    "disk_drives": (
        ["disk drives", "list my drives", "show disk drives",
         "how much disk space do i have left", "free space on my drives",
         "what storage do i have", "check drive space", "how full is my disk"],
        ["am i running out of storage", "how much room is left on this thing",
         "show me the partitions"],
    ),
    "list_processes": (
        ["list processes", "show running processes", "what is running",
         "whats hogging the memory", "show me cpu usage by process",
         "which apps are using resources", "top processes"],
        ["what's eating my ram", "show me what's chewing cpu"],
    ),
    "create_file": (
        ["create a file called notes.txt", "make a file named report.txt",
         "create a file called todo.txt with content buy milk",
         "write a file named log.txt", "new file called scratch.txt",
         "make me a file called ideas.txt with content brainstorm"],
        ["knock up a file called draft.txt", "start a new file named memo.txt"],
    ),
    "search_files": (
        ["search for files named report", "find files called invoice",
         "look for files matching budget", "search my files for notes",
         "find the file named contract", "locate files named summary"],
        ["dig up any file called receipt", "hunt for files named proposal"],
    ),
    "list_files": (
        ["show me my files", "list files", "what files are here",
         "list the files in downloads", "show files on my desktop"],
        ["what have i got in this folder", "give me a directory listing"],
    ),
    "organize_folder": (
        ["organize my downloads folder", "tidy up my downloads",
         "sort out my desktop", "clean up the downloads folder",
         "organize files on my desktop"],
        ["sort my downloads into folders", "put my desktop in order"],
    ),
    "create_task": (
        ["create a task named call supplier", "add a task to review budget",
         "new task called send invoice", "make a task named follow up",
         "create a task to book flights"],
        ["put a task on my list called order stock",
         "remind me to do the quarterly review as a task"],
    ),
    "list_tasks": (
        ["list tasks", "show my tasks", "what tasks do i have",
         "summarise my tasks", "show the task list", "whats on my task list"],
        ["what have i got to do", "run through my outstanding tasks"],
    ),
    "add_team_member": (
        ["add priya to the team", "add sam to the team",
         "register alice into the team", "onboard bob to the team"],
        ["put ravi on the team", "bring maya into the team"],
    ),
    "create_document": (
        ["create a document about machine learning",
         "write a report on renewable energy",
         "make a document about quarterly results",
         "draft a document on market trends",
         "generate a report about customer feedback"],
        ["put together a write-up on supply chain risk",
         "produce a document covering hiring plans"],
    ),
    "create_spreadsheet": (
        ["create a spreadsheet of my tasks", "make an excel of my projects",
         "export a spreadsheet of the team", "generate an xlsx of my tasks"],
        ["build me a spreadsheet from my task list"],
    ),
    "screenshot": (
        ["take a screenshot", "capture my screen", "grab a screenshot",
         "screenshot this", "take a picture of my screen"],
        ["snap the screen for me", "capture what's displayed"],
    ),
    "extract_text": (
        ["read the text on my screen", "what text is on my screen",
         "extract text from my screen", "ocr my screen"],
        ["read out what's written on screen", "pull the text off my display"],
    ),
    "open_application": (
        ["open notepad", "launch calculator", "start chrome",
         "open the browser", "run notepad"],
        ["fire up notepad", "get chrome going"],
    ),
    "command_history": (
        ["show command history", "what did i run recently",
         "list recent commands", "show my history"],
        ["what have i been running", "recap my recent commands"],
    ),
}


def _label_for(controller, command: str) -> str:
    """Ask the system's own parser what this is - never label it myself."""
    try:
        intent = controller._parse_direct_command(command)
    except Exception:
        return ""
    return (intent or {}).get("type", "") or ""


def build_examples(controller, split: int) -> Tuple[List[dict], List[Tuple[str, str]], dict]:
    """Return (training experiences, held-out pairs, corpus stats)."""
    train_experiences: List[dict] = []
    holdout: List[Tuple[str, str]] = []
    stats = {"intents": 0, "train_kept": 0, "train_dropped": 0, "holdout": 0}

    for intent_type, (train_phrases, eval_phrases) in CORPUS.items():
        stats["intents"] += 1

        for phrase in train_phrases:
            actual = _label_for(controller, phrase)
            # Keep only what the parser ALREADY gets right; a mislabelled
            # example would teach the model the parser's mistakes.
            if actual != intent_type:
                stats["train_dropped"] += 1
                continue
            stats["train_kept"] += 1
            train_experiences.append({
                "command": phrase,
                "timestamp": datetime.now().isoformat(),
                "intent_type": intent_type,
                "strategy": {"tier": "direct", "complexity": "simple",
                             "intent": {"type": intent_type}},
                "result": {"success": True},
                "reward": 1.0,
            })

        for phrase in eval_phrases:
            holdout.append((phrase, intent_type))
            stats["holdout"] += 1

    return train_experiences, holdout, stats


def score_holdout(model, holdout: List[Tuple[str, str]]) -> dict:
    """How often does the model land on the right route for unseen wording?"""
    from benchmark.route_map import route_for

    correct, unknown, rows = 0, 0, []
    for phrase, intent_type in holdout:
        want = route_for(intent_type)
        try:
            got = (model.predict(phrase) or {}).get("predicted_route") or ""
        except Exception:
            got = ""
        hit = bool(got) and got == want
        if not got or got == "unknown":
            unknown += 1
        correct += hit
        rows.append({"phrase": phrase, "want": want, "got": got, "hit": hit})
    total = len(holdout) or 1
    return {"correct": correct, "total": len(holdout),
            "accuracy": round(correct / total, 3),
            "unknown": unknown, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    random.seed(args.seed)

    import main as m

    controller = m.AutonomousSystemController()
    train_experiences, holdout, stats = build_examples(controller, split=0)

    print("\n" + "=" * 68)
    print("TRAINING CORPUS")
    print("=" * 68)
    print(f"  intents            {stats['intents']}")
    print(f"  training examples  {stats['train_kept']}"
          f"   (dropped {stats['train_dropped']} the parser mislabels)")
    print(f"  held-out phrasings {stats['holdout']}  (never trained on)")

    if args.dry_run:
        print("\n  --dry-run: nothing was fitted\n")
        return 0

    learning = controller.agents["learning"]
    model = learning.phase5_model.neural_command_model

    before = score_holdout(model, holdout)
    print(f"\n  held-out accuracy BEFORE  {before['accuracy']:.1%}"
          f"  ({before['correct']}/{before['total']}, {before['unknown']} unknown)")

    # Fit on the bootstrap corpus PLUS whatever real history exists, so the
    # user's own usage is not thrown away by this.
    try:
        existing = learning.replay.all()
    except Exception:
        existing = []
    combined = list(existing) + train_experiences
    print(f"  fitting on {len(combined)} experiences "
          f"({len(existing)} real + {len(train_experiences)} bootstrap)...")

    fit = model.fit(combined)
    metrics = (fit or {}).get("metrics", {})
    print(f"  model: {fit.get('model_type')}  trained={fit.get('trained')}  "
          f"acc={metrics.get('accuracy')}  labels={len(fit.get('labels') or [])}")

    after = score_holdout(model, holdout)
    print(f"\n  held-out accuracy AFTER   {after['accuracy']:.1%}"
          f"  ({after['correct']}/{after['total']}, {after['unknown']} unknown)")

    delta = after["accuracy"] - before["accuracy"]
    print(f"  change                    {delta:+.1%}")

    misses = [r for r in after["rows"] if not r["hit"]]
    if misses:
        print(f"\n  still wrong on {len(misses)} unseen phrasings:")
        for r in misses[:10]:
            print(f"    {r['phrase'][:44]:46} want={r['want']:14} got={r['got'] or '-'}")

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (RESULTS_DIR / f"{stamp}_training.json").write_text(json.dumps({
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "corpus": stats, "before": before, "after": after,
        "delta": round(delta, 3), "fit_metrics": metrics,
    }, indent=2), encoding="utf-8")
    print(f"\n  saved to benchmark/results/{stamp}_training.json\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
