"""
Build a labelled intent corpus from ASC's current deterministic parser.

The parser is used as the labelling oracle so this dataset captures what the
system already knows before a learned classifier tries to generalise beyond it.
"""

from __future__ import annotations

import ast
import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main as asc_module  # noqa: E402


CONFIG_PATH = PROJECT_ROOT / "config" / "settings.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "intent_corpus.jsonl"
EPISODIC_DB = PROJECT_ROOT / "data" / "episodic_memory.db"
MIN_PER_INTENT = 20
PARAPHRASE_MODEL = "qwen2.5:3b"
OLLAMA_PARAPHRASE_BUDGET = 6


def _controller():
    controller = object.__new__(asc_module.AutonomousSystemController)
    controller.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return controller


def _label(command: str, controller=None) -> Optional[str]:
    controller = controller or _controller()
    try:
        intent = controller._parse_direct_command(command)
    except Exception:
        return None
    return (intent or {}).get("type")


def _seed_from_benchmark_tasks() -> List[str]:
    from benchmark.tasks import TASKS

    return [task.command for task in TASKS if getattr(task, "command", None)]


def _seed_from_multistep() -> List[str]:
    from benchmark.multistep import MULTISTEP

    return [task["command"] for task in MULTISTEP if task.get("command")]


def _seed_from_intent_matrix() -> List[str]:
    matrix_path = PROJECT_ROOT / "tests" / "test_intent_matrix.py"
    source = matrix_path.read_text(encoding="utf-8")
    main_source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    pair_re = re.compile(
        r'if any\(phrase in normalized for phrase in \[(?P<phrases>[^\]]+)\]\):\s*\n\s*return \{"type": "(?P<intent>[a-z_]+)"'
    )
    phrase_re = re.compile(r'"([^"]+)"')
    seeds = []
    for match in pair_re.finditer(main_source):
        seeds.extend(phrase_re.findall(match.group("phrases")))

    literal_re = re.compile(r"_parse_direct_command\(\s*['\"]([^'\"]+)['\"]")
    seeds.extend(literal_re.findall(source))
    return seeds


def _seed_from_episodes() -> List[str]:
    if not EPISODIC_DB.exists():
        return []

    commands: List[str] = []
    with sqlite3.connect(EPISODIC_DB) as conn:
        for table, column in [
            ("episodes", "task"),
            ("tasks", "command"),
            ("execution_journal", "command"),
        ]:
            if _has_table(conn, table) and _has_column(conn, table, column):
                rows = conn.execute(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
                commands.extend(str(row[0]) for row in rows if row and row[0])

        if _has_table(conn, "command_history") and _has_column(conn, "command_history", "data"):
            rows = conn.execute("SELECT data FROM command_history").fetchall()
            for (payload,) in rows:
                try:
                    data = json.loads(payload)
                except Exception:
                    continue
                command = data.get("command")
                if command:
                    commands.append(str(command))
    return commands


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _dedupe(items: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        clean = " ".join((item or "").strip().split())
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out


def _ollama_paraphrases(command: str, intent: str, host: str, limit: int = 4) -> List[str]:
    prompt = (
        "Create short paraphrases for an intent-classifier dataset.\n"
        f"Intent label: {intent}\n"
        f"Original command: {command}\n"
        "Include spoken-style phrasing, one typo/misspelling, and one contraction if natural.\n"
        "Return only a JSON list of strings."
    )
    try:
        response = requests.post(
            f"{host}/api/generate",
            json={
                "model": PARAPHRASE_MODEL,
                "prompt": prompt,
                "stream": False,
                "keep_alive": 0,
                "options": {"num_gpu": 0, "num_predict": 220, "temperature": 0.7},
            },
            timeout=10,
        )
        if response.status_code != 200:
            return []
        text = response.json().get("response", "").strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start < 0 or end <= start:
            return []
        parsed = ast.literal_eval(text[start:end])
        if not isinstance(parsed, list):
            return []
        return _dedupe(str(item) for item in parsed)[:limit]
    except Exception:
        return []


def _has_ollama_model(host: str, model: str) -> bool:
    try:
        response = requests.get(f"{host}/api/tags", timeout=2)
        if response.status_code != 200:
            return False
        models = response.json().get("models", [])
        return any(item.get("name") == model or item.get("name", "").split(":")[0] == model for item in models)
    except Exception:
        return False


def _deterministic_paraphrases(command: str) -> List[str]:
    variants = [
        f"please {command}",
        f"can you {command}",
        f"could you {command}",
    ]
    lower = command.lower()
    replacements = {
        "show": "tell me",
        "create": "make",
        "list": "show me",
        "search": "look for",
        "delete": "remove",
        "system": "systm",
        "remember": "remeber",
        "because": "cause",
    }
    for source, target in replacements.items():
        if source in lower:
            variants.append(re.sub(source, target, command, count=1, flags=re.IGNORECASE))
    if "do not" in lower:
        variants.append(re.sub("do not", "don't", command, count=1, flags=re.IGNORECASE))
    if "what is" in lower:
        variants.append(re.sub("what is", "what's", command, count=1, flags=re.IGNORECASE))
    return _dedupe(variants)


def collect_seed_commands() -> List[str]:
    return _dedupe(
        [
            *_seed_from_benchmark_tasks(),
            *_seed_from_multistep(),
            *_seed_from_intent_matrix(),
            *_seed_from_episodes(),
        ]
    )


def build_corpus(use_ollama: bool = True) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    controller = _controller()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    host = config.get("ollama", {}).get("host", "http://127.0.0.1:11434")
    ollama_available = use_ollama and _has_ollama_model(host, PARAPHRASE_MODEL)
    ollama_used = 0

    labelled: Dict[Tuple[str, str], Dict[str, str]] = {}
    for seed in collect_seed_commands():
        intent = _label(seed, controller)
        if not intent:
            continue
        labelled[(seed.lower(), intent)] = {"command": seed, "intent": intent}

        paraphrases = _deterministic_paraphrases(seed)
        if ollama_available and ollama_used < OLLAMA_PARAPHRASE_BUDGET:
            paraphrases.extend(_ollama_paraphrases(seed, intent, host))
            ollama_used += 1

        for paraphrase in paraphrases:
            labelled[(paraphrase.lower(), intent)] = {"command": paraphrase, "intent": intent}

    corpus = sorted(labelled.values(), key=lambda item: (item["intent"], item["command"].lower()))
    counts = Counter(item["intent"] for item in corpus)
    return corpus, dict(sorted(counts.items()))


def write_corpus(corpus: Sequence[Dict[str, str]], path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for item in corpus:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the ASC intent corpus.")
    parser.add_argument(
        "--ollama",
        action="store_true",
        help=f"Use {PARAPHRASE_MODEL} for a small paraphrase expansion budget.",
    )
    args = parser.parse_args()

    corpus, counts = build_corpus(use_ollama=args.ollama)
    write_corpus(corpus)

    print(f"Wrote {len(corpus)} labelled examples to {OUTPUT_PATH}")
    if args.ollama:
        print(f"Ollama paraphrase expansion enabled with model {PARAPHRASE_MODEL}.")
    else:
        print("Ollama paraphrase expansion skipped by default; rerun with --ollama for model-generated variants.")
    print("\nPer-intent counts:")
    for intent, count in counts.items():
        marker = "LOW" if count < MIN_PER_INTENT else "OK"
        print(f"  {intent:30} {count:4} {marker}")

    low = {intent: count for intent, count in counts.items() if count < MIN_PER_INTENT}
    if low:
        print("\nIntents below 20 examples:")
        for intent, count in low.items():
            print(f"  {intent}: {count}")
    else:
        print("\nAll discovered intents have at least 20 examples.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
