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
import random
from collections import Counter, defaultdict
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
MIN_PER_INTENT = 40
MAX_PER_INTENT = 150
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


def _dedupe_examples(items: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out = []
    for item in items:
        command = " ".join((item.get("command") or "").strip().split())
        intent = (item.get("intent") or "").strip()
        key = (command.lower(), intent)
        if command and intent and key not in seen:
            seen.add(key)
            out.append({"command": command, "intent": intent})
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


def _targeted_paraphrases(command: str) -> List[str]:
    """Create broad but parser-checkable variants for data-starved intents."""

    prefixes = [
        "",
        "please",
        "can you",
        "could you",
        "hey vega",
        "i need you to",
        "quickly",
        "for me",
        "would you",
        "when you can",
        "right now",
        "please quickly",
    ]
    suffixes = [
        "",
        "please",
        "now",
        "for me",
        "on this computer",
        "using the current context",
        "when possible",
        "and tell me when it is done",
        "without extra questions",
        "with default settings",
        "from here",
        "in this session",
    ]
    spoken = [
        command.replace("show", "tell me", 1),
        command.replace("create", "make", 1),
        command.replace("list", "show me", 1),
        command.replace("search", "look for", 1),
        command.replace("remember", "remeber", 1),
        f"uh {command}",
        f"{command} pls",
        f"{command} real quick",
    ]

    variants = list(spoken)
    for prefix in prefixes:
        for suffix in suffixes:
            parts = [prefix, command, suffix]
            variants.append(" ".join(part for part in parts if part).strip())
    return _dedupe(variants)


def _intent_specific_paraphrases(intent: str, command: str) -> List[str]:
    """Fill sparse parser patterns with realistic values instead of duplicates."""

    if intent == "calculate":
        expressions = [
            "2 plus 2",
            "25 times 4",
            "144 divided by 12",
            "17 percent of 4500",
            "the square root of 144",
            "50 minus 18",
            "9 multiplied by 8",
            "100 divided by 4",
            "12 plus 30",
            "5 squared",
        ]
        return [f"{lead} {expr}".strip() for expr in expressions for lead in ["what is", "calculate", "compute", "evaluate"]]
    if intent == "dns_lookup":
        hosts = ["localhost", "google.com", "github.com", "openai.com", "example.com", "amazon.com", "microsoft.com", "python.org"]
        return [f"{lead} {host}".strip() for host in hosts for lead in ["dns lookup for", "lookup dns for", "resolve dns for", "please dns lookup for", "can you dns lookup for"]]
    if intent == "environment_variable":
        variables = ["PATH", "TEMP", "USERNAME", "USERPROFILE", "APPDATA", "COMPUTERNAME", "OS", "PROCESSOR_ARCHITECTURE"]
        return [f"{lead} {var}".strip() for var in variables for lead in ["show environment variable", "get environment variable", "print environment variable", "please show environment variable", "can you show environment variable"]]
    if intent == "open_folder":
        folders = ["downloads", "documents", "desktop", "pictures", "home", "download", "document"]
        return [f"{lead} {folder} folder".strip() for folder in folders for lead in ["open the", "open", "please open the", "can you open the", "launch the"]]
    if intent == "security_port_scan":
        targets = ["127.0.0.1", "localhost", "192.168.1.1", "example.com", "github.com"]
        ports = ["80-82", "443", "22-25", "8000-8002", "3000"]
        return [f"{lead} {target} ports {port}" for target in targets for port in ports for lead in ["run security scan on", "security scan", "port scan"]]
    if intent == "security_ssl_check":
        hosts = ["github.com", "google.com", "openai.com", "example.com", "amazon.com", "microsoft.com", "python.org", "wikipedia.org"]
        return [f"{lead} {host}".strip() for host in hosts for lead in ["check ssl on", "ssl check for", "verify ssl on", "please check ssl on", "can you check ssl on"]]
    if intent == "system_command":
        commands = ["Get-Date", "Get-Location", "whoami", "hostname", "ipconfig", "dir", "echo hello", "Get-Process", "Get-ChildItem", "pwd"]
        return [f"{lead} {cmd}".strip() for cmd in commands for lead in ["run powershell", "execute powershell", "please run powershell", "can you run powershell"]]
    if intent == "system_power_action":
        actions = ["shutdown", "restart", "sleep", "hibernate", "lock"]
        return [f"{lead} {action} system".strip() for action in actions for lead in ["", "please", "can you", "could you", "i need you to"]]
    if intent == "transcription_noise":
        noises = [
            "(keyboard clicking)",
            "[keyboard clicking]",
            "(background noise)",
            "[background noise]",
            "(typing sounds)",
            "[typing sounds]",
            "(mouse click)",
            "[mouse click]",
            "(static)",
            "[static]",
            "(silence)",
            "[silence]",
        ]
        return [f"{prefix} {noise} {suffix}".strip() for noise in noises for prefix in ["", "uh", "um", "sorry"] for suffix in ["", "again", "there"]]
    return [command]


def collect_seed_commands() -> List[str]:
    return _dedupe(
        [
            *_seed_from_benchmark_tasks(),
            *_seed_from_multistep(),
            *_seed_from_intent_matrix(),
            *_seed_from_episodes(),
        ]
    )


def _build_raw_corpus(use_ollama: bool) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
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


def _balance_corpus(raw_corpus: Sequence[Dict[str, str]], use_ollama: bool) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    controller = _controller()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    host = config.get("ollama", {}).get("host", "http://127.0.0.1:11434")
    ollama_available = use_ollama and _has_ollama_model(host, PARAPHRASE_MODEL)
    ollama_used = 0

    by_intent: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for item in _dedupe_examples(raw_corpus):
        by_intent[item["intent"]].append(item)

    balanced: List[Dict[str, str]] = []
    rng = random.Random(11)
    for intent in sorted(by_intent):
        examples = _dedupe_examples(by_intent[intent])
        if len(examples) < MIN_PER_INTENT:
            seeds = list(examples)
            for seed in seeds:
                for paraphrase in _intent_specific_paraphrases(intent, seed["command"]):
                    if len(examples) >= MIN_PER_INTENT:
                        break
                    if _label(paraphrase, controller) == intent:
                        examples.append({"command": paraphrase, "intent": intent})
                        examples = _dedupe_examples(examples)
                if len(examples) >= MIN_PER_INTENT:
                    break
            for seed in seeds:
                for paraphrase in _targeted_paraphrases(seed["command"]):
                    if len(examples) >= MIN_PER_INTENT:
                        break
                    # Parser verification is the guardrail: if a variant now
                    # routes elsewhere, it is training poison and gets dropped.
                    if _label(paraphrase, controller) == intent:
                        examples.append({"command": paraphrase, "intent": intent})
                        examples = _dedupe_examples(examples)
                if len(examples) >= MIN_PER_INTENT:
                    break

            if ollama_available and len(examples) < MIN_PER_INTENT and ollama_used < OLLAMA_PARAPHRASE_BUDGET:
                for seed in seeds:
                    for paraphrase in _ollama_paraphrases(seed["command"], intent, host, limit=10):
                        if len(examples) >= MIN_PER_INTENT:
                            break
                        if _label(paraphrase, controller) == intent:
                            examples.append({"command": paraphrase, "intent": intent})
                            examples = _dedupe_examples(examples)
                    ollama_used += 1
                    if len(examples) >= MIN_PER_INTENT or ollama_used >= OLLAMA_PARAPHRASE_BUDGET:
                        break

        if len(examples) > MAX_PER_INTENT:
            rng.shuffle(examples)
            examples = sorted(examples[:MAX_PER_INTENT], key=lambda item: item["command"].lower())
        balanced.extend(examples)

    corpus = sorted(_dedupe_examples(balanced), key=lambda item: (item["intent"], item["command"].lower()))
    counts = Counter(item["intent"] for item in corpus)
    return corpus, dict(sorted(counts.items()))


def build_corpus(use_ollama: bool = True) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    raw_corpus, _ = _build_raw_corpus(use_ollama=use_ollama)
    return _balance_corpus(raw_corpus, use_ollama=use_ollama)


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

    raw_corpus, before_counts = _build_raw_corpus(use_ollama=args.ollama)
    corpus, counts = _balance_corpus(raw_corpus, use_ollama=args.ollama)
    write_corpus(corpus)

    print(f"Wrote {len(corpus)} labelled examples to {OUTPUT_PATH}")
    if args.ollama:
        print(f"Ollama paraphrase expansion enabled with model {PARAPHRASE_MODEL}.")
    else:
        print("Ollama paraphrase expansion skipped by default; rerun with --ollama for model-generated variants.")
    print("\nDistribution before balancing:")
    for intent, count in before_counts.items():
        marker = "LOW" if count < MIN_PER_INTENT else "OK"
        print(f"  {intent:30} {count:4} {marker}")

    print("\nDistribution after balancing:")
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
