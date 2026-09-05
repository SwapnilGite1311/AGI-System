"""Evaluate deterministic and learned intent routing strategies."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main as asc_module  # noqa: E402
from learning.intent_classifier import CORPUS_PATH, IntentClassifier, _read_rows, _split_rows  # noqa: E402


CONFIG_PATH = PROJECT_ROOT / "config" / "settings.json"


def _controller():
    controller = object.__new__(asc_module.AutonomousSystemController)
    try:
        controller.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        controller.config = {}
    return controller


def _regex_predict(controller, command: str) -> str:
    try:
        intent = controller._parse_direct_command(command)
    except Exception:
        intent = None
    return (intent or {}).get("type") or "unknown"


def _score(rows: List[Dict[str, str]], predictor: Callable[[str], str]) -> Dict[str, float]:
    correct = 0
    latencies = []
    for row in rows:
        start = time.perf_counter()
        predicted = predictor(row["command"])
        latencies.append((time.perf_counter() - start) * 1000)
        if predicted == row["intent"]:
            correct += 1
    return {
        "accuracy": round(correct / len(rows), 4) if rows else 0.0,
        "mean_latency_ms": round(statistics.fmean(latencies), 4) if latencies else 0.0,
    }


def run_eval(corpus_path: Path = CORPUS_PATH) -> Dict[str, Dict[str, float]]:
    rows = _read_rows(corpus_path)
    if not rows:
        raise ValueError(f"No intent corpus found at {corpus_path}")

    _, heldout = _split_rows(rows, holdout=0.2, seed=7)
    controller = _controller()
    classifier = IntentClassifier()
    classifier.train(rows, holdout=0.2, seed=7)

    def regex_only(command: str) -> str:
        return _regex_predict(controller, command)

    def classifier_only(command: str) -> str:
        return str(classifier.predict(command)["intent"])

    def regex_then_classifier(command: str) -> str:
        regex_intent = _regex_predict(controller, command)
        if regex_intent != "unknown":
            return regex_intent
        return str(classifier.predict(command)["intent"])

    return {
        "regex_only": _score(heldout, regex_only),
        "classifier_only": _score(heldout, classifier_only),
        "regex_then_classifier": _score(heldout, regex_then_classifier),
    }


def main() -> int:
    results = run_eval()
    print("Intent routing benchmark on stratified 20% holdout")
    for name, metrics in results.items():
        print(
            f"{name:24} accuracy={metrics['accuracy']:.4f} "
            f"mean_latency_ms={metrics['mean_latency_ms']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
