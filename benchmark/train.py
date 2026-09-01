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
         "give me a system report", "what are my system specs",
         "system diagnostics", "report on this machine", "machine health",
         "show system details", "how is the computer performing",
         "give me machine information", "current system state"],
        ["how's my computer holding up", "run a health check on this machine",
         "tell me about this pc", "is everything running okay",
         "give me the rundown on this box"],
    ),
    "disk_drives": (
        ["disk drives", "list my drives", "show disk drives",
         "how much disk space do i have left", "free space on my drives",
         "what storage do i have", "check drive space", "how full is my disk",
         "show storage capacity", "disk usage by drive", "list volumes",
         "remaining disk space", "how much storage is free",
         "check my hard drive space", "show me the drives"],
        ["am i running out of storage", "how much room is left on this thing",
         "show me the partitions", "is my disk nearly full",
         "what's my free capacity"],
    ),
    "list_processes": (
        ["list processes", "show running processes", "what is running",
         "whats hogging the memory", "show me cpu usage by process",
         "which apps are using resources", "top processes",
         "what programs are running", "show active processes",
         "list running applications", "which process uses most cpu",
         "show me resource usage per app"],
        ["what's eating my ram", "show me what's chewing cpu",
         "which program is slowing things down", "what's running right now"],
    ),
    "create_file": (
        ["create a file called notes.txt", "make a file named report.txt",
         "create a file called todo.txt with content buy milk",
         "write a file named log.txt", "new file called scratch.txt",
         "make me a file called ideas.txt with content brainstorm",
         "create a text file called summary.txt",
         "generate a file named output.txt", "save a file called draft.txt",
         "create notes.txt with content hello"],
        ["knock up a file called draft.txt", "start a new file named memo.txt",
         "put together a file called plan.txt"],
    ),
    "search_files": (
        ["search for files named report", "find files called invoice",
         "look for files matching budget", "search my files for notes",
         "find the file named contract", "locate files named summary",
         "search my computer for photos", "where is my resume file",
         "do i have a file called taxes", "find any file named backup",
         "search my laptop for invoices", "look on my drive for archives"],
        ["dig up any file called receipt", "hunt for files named proposal",
         "track down my file called ledger", "is there a file named agenda"],
    ),
    "list_files": (
        ["show me my files", "list files", "what files are here",
         "list the files in downloads", "show files on my desktop",
         "display my files", "show directory contents", "list what is here"],
        ["what have i got in this folder", "give me a directory listing",
         "show me what's in here"],
    ),
    "organize_folder": (
        ["organize my downloads folder", "tidy up my downloads",
         "sort out my desktop", "clean up the downloads folder",
         "organize files on my desktop", "tidy my documents folder",
         "arrange my downloads by type", "clean up my desktop files"],
        ["sort my downloads into folders", "put my desktop in order",
         "get my downloads under control"],
    ),
    "create_task": (
        ["create a task named call supplier", "add a task to review budget",
         "new task called send invoice", "make a task named follow up",
         "create a task to book flights", "add task called write report",
         "create a task titled prepare slides", "new task order supplies"],
        ["put a task on my list called order stock",
         "remind me to do the quarterly review as a task",
         "stick a task on there called chase invoice"],
    ),
    "list_tasks": (
        ["list tasks", "show my tasks", "what tasks do i have",
         "summarise my tasks", "show the task list", "whats on my task list",
         "display my tasks", "show all tasks", "what is on my list",
         "how many tasks do i have"],
        ["what have i got to do", "run through my outstanding tasks",
         "give me my to-do list"],
    ),
    "complete_task": (
        ["mark call supplier as done", "set review budget as complete",
         "mark the invoice task as finished", "complete the task send report",
         "flag write summary as done", "mark book flights as completed"],
        ["tick off the task called chase invoice",
         "close out the task named prepare slides"],
    ),
    "add_team_member": (
        ["add priya to the team", "add sam to the team",
         "register alice into the team", "onboard bob to the team",
         "add nadia to the team", "add omar to the staff",
         "add lena to team with email lena@example.com"],
        ["put ravi on the team", "bring maya into the team",
         "sign up dev to the roster"],
    ),
    "list_team": (
        ["list team", "show me the team", "who is on the team",
         "display team members", "show the team list", "list team members"],
        ["who have i got working on this", "run through the team"],
    ),
    "create_document": (
        ["create a document about machine learning",
         "write a report on renewable energy",
         "make a document about quarterly results",
         "draft a document on market trends",
         "generate a report about customer feedback",
         "create a document about supply chains",
         "write a report covering hiring plans",
         "prepare a document on risk assessment"],
        ["put together a write-up on supply chain risk",
         "produce a document covering hiring plans",
         "draft me something on competitor analysis"],
    ),
    "create_spreadsheet": (
        ["create a spreadsheet of my tasks", "make an excel of my projects",
         "export a spreadsheet of the team", "generate an xlsx of my tasks",
         "build a spreadsheet from my tasks", "export my projects to excel"],
        ["build me a spreadsheet from my task list",
         "get my tasks into a spreadsheet"],
    ),
    "screenshot": (
        ["take a screenshot", "capture my screen", "grab a screenshot",
         "screenshot this", "take a picture of my screen",
         "capture the screen", "screenshot my display"],
        ["snap the screen for me", "capture what's displayed",
         "get me a picture of the screen"],
    ),
    "extract_text": (
        ["read the text on my screen", "what text is on my screen",
         "extract text from my screen", "ocr my screen",
         "read my screen", "get the text off my screen"],
        ["read out what's written on screen", "pull the text off my display",
         "what does the screen say"],
    ),
    "open_application": (
        ["open notepad", "launch calculator", "start chrome",
         "open the browser", "run notepad", "launch notepad",
         "start the calculator", "open chrome browser"],
        ["fire up notepad", "get chrome going", "boot up the calculator"],
    ),
    "open_file": (
        ["open my_tasks.xlsx", "open the file report.pdf",
         "open budget.xlsx from desktop", "open notes.txt",
         "just open summary.docx from documents folder",
         "open the document plan.docx"],
        ["pull up the file called ledger.xlsx",
         "let me see notes.txt"],
    ),
    "command_history": (
        ["show command history", "what did i run recently",
         "list recent commands", "show my history",
         "display command history", "what commands have i run"],
        ["what have i been running", "recap my recent commands"],
    ),
    "self_report": (
        ["what can you do", "tell me what you can do",
         "which model are you using", "what model are you running",
         "in which folder are you situated", "where are your files",
         "list your capabilities", "what are you able to do"],
        ["what are you actually capable of", "which llm is behind you",
         "whereabouts do you live on disk"],
    ),
    "network_status": (
        ["show network status", "check my network", "network information",
         "is my internet working", "show connection status",
         "check network connection"],
        ["how's my wifi doing", "am i online"],
    ),
    "productivity_report": (
        ["productivity metrics", "show productivity report",
         "generate a productivity report", "how productive have i been",
         "show my productivity stats"],
        ["give me a productivity summary", "how am i doing on output"],
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
