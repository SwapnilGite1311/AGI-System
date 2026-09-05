"""Learned intent classifier for ASC commands.

This module deliberately avoids hard runtime dependencies on Ollama, sklearn,
or torch. It uses `core.embeddings.embed` when `nomic-embed-text` is available
and falls back to character n-gram vectors otherwise.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.embeddings import DEFAULT_MODEL, embed  # noqa: E402


CORPUS_PATH = PROJECT_ROOT / "data" / "intent_corpus.jsonl"
MODEL_PATH = PROJECT_ROOT / "data" / "intent_classifier.json"
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.json"


def _read_rows(path: Path) -> List[Dict[str, str]]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            command = " ".join(str(item.get("command", "")).split())
            intent = str(item.get("intent", "")).strip()
            if command and intent:
                rows.append({"command": command, "intent": intent})
    return rows


def _host_from_config() -> str:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return config.get("ollama", {}).get("host", "http://127.0.0.1:11434")
    except Exception:
        return "http://127.0.0.1:11434"


def _split_rows(rows: Sequence[Dict[str, str]], holdout: float, seed: int) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    rng = random.Random(seed)
    groups: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["intent"]].append(row)

    train: List[Dict[str, str]] = []
    test: List[Dict[str, str]] = []
    for intent_rows in groups.values():
        shuffled = list(intent_rows)
        rng.shuffle(shuffled)
        if len(shuffled) < 2:
            train.extend(shuffled)
            continue
        holdout_count = max(1, int(round(len(shuffled) * holdout)))
        holdout_count = min(holdout_count, len(shuffled) - 1)
        test.extend(shuffled[:holdout_count])
        train.extend(shuffled[holdout_count:])
    return train, test


def _ngrams(text: str, min_n: int = 3, max_n: int = 5) -> Iterable[str]:
    clean = f" {text.lower().strip()} "
    for n in range(min_n, max_n + 1):
        for index in range(0, max(0, len(clean) - n + 1)):
            yield clean[index : index + n]


def _normalise(vector: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [float(value) / norm for value in vector]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


class IntentClassifier:
    """Small learned classifier with embedding and char-ngram feature backends."""

    def __init__(
        self,
        model_path: Path | str = MODEL_PATH,
        max_features: int = 1200,
        host: Optional[str] = None,
        embedding_model: str = DEFAULT_MODEL,
    ):
        self.model_path = Path(model_path)
        self.max_features = max_features
        self.host = host or _host_from_config()
        self.embedding_model = embedding_model
        self.feature_type = "char_ngrams"
        self.vocab: Dict[str, int] = {}
        self.labels: List[str] = []
        self.centroids: Dict[str, List[float]] = {}
        self.metrics: Dict[str, object] = {}
        self._trained = False
        self.holdout_rows: List[Dict[str, str]] = []

    def train(
        self,
        rows_or_path: Sequence[Dict[str, str]] | Path | str = CORPUS_PATH,
        holdout: float = 0.2,
        seed: int = 7,
        use_embeddings: bool = True,
    ) -> Dict[str, object]:
        rows = _read_rows(Path(rows_or_path)) if isinstance(rows_or_path, (str, Path)) else list(rows_or_path)
        if not rows:
            raise ValueError("No intent training rows found.")

        train_rows, test_rows = _split_rows(rows, holdout, seed)
        self.holdout_rows = test_rows
        self.labels = sorted({row["intent"] for row in train_rows})

        vectors = self._fit_vectors(train_rows, use_embeddings=use_embeddings)
        sums: Dict[str, List[float]] = {}
        counts: Counter[str] = Counter()
        for row, vector in zip(train_rows, vectors):
            label = row["intent"]
            counts[label] += 1
            if label not in sums:
                sums[label] = [0.0 for _ in vector]
            for index, value in enumerate(vector):
                sums[label][index] += value

        self.centroids = {
            label: _normalise([value / max(1, counts[label]) for value in vector])
            for label, vector in sums.items()
        }
        self._trained = True
        self.metrics = self.evaluate(test_rows)
        self.metrics["feature_type"] = self.feature_type
        self.metrics["train_examples"] = len(train_rows)
        self.metrics["holdout_examples"] = len(test_rows)
        return self.metrics

    def predict(self, command: str) -> Dict[str, object]:
        if not self._trained or not self.centroids:
            return {"intent": "unknown", "confidence": 0.0, "alternatives": []}

        vector = self._vectorise(command)
        scored = sorted(
            ((label, _cosine(vector, centroid)) for label, centroid in self.centroids.items()),
            key=lambda item: item[1],
            reverse=True,
        )
        if not scored:
            return {"intent": "unknown", "confidence": 0.0, "alternatives": []}

        scores = [score for _, score in scored]
        confidence = self._confidence(scores)
        alternatives = [{"intent": label, "score": round(score, 4)} for label, score in scored[1:4]]
        # Margin discriminates far better than the softmax confidence does.
        # Over 103 classes the softmax is compressed - a correct prediction
        # often sits near 0.25 - so thresholding on it either never fires or
        # fires on guesses. How far the winner beats the runner-up separates
        # "this is clearly X" from "it could be any of these" much more
        # cleanly: measured on the rules' misses, margin >= 0.12 answered 17
        # and got all 17 right, where confidence >= 0.40 answered only 9.
        margin = round(scored[0][1] - scored[1][1], 4) if len(scored) > 1 else 1.0
        return {
            "intent": scored[0][0],
            "confidence": confidence,
            "score": round(scored[0][1], 4),
            "margin": margin,
            "alternatives": alternatives,
        }

    def save(self, path: Path | str | None = None) -> None:
        target = Path(path) if path else self.model_path
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "feature_type": self.feature_type,
            "vocab": self.vocab,
            "labels": self.labels,
            "centroids": self.centroids,
            "metrics": self.metrics,
            "max_features": self.max_features,
            "host": self.host,
            "embedding_model": self.embedding_model,
        }
        target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def load(self, path: Path | str | None = None) -> bool:
        source = Path(path) if path else self.model_path
        if not source.exists():
            return False
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
            self.feature_type = payload.get("feature_type", "char_ngrams")
            self.vocab = {str(key): int(value) for key, value in payload.get("vocab", {}).items()}
            self.labels = [str(label) for label in payload.get("labels", [])]
            self.centroids = {
                str(label): [float(value) for value in vector]
                for label, vector in payload.get("centroids", {}).items()
            }
            self.metrics = payload.get("metrics", {})
            self.max_features = int(payload.get("max_features", self.max_features))
            self.host = payload.get("host", self.host)
            self.embedding_model = payload.get("embedding_model", self.embedding_model)
            self._trained = bool(self.centroids)
            return self._trained
        except Exception:
            self._trained = False
            return False

    def evaluate(self, rows: Sequence[Dict[str, str]]) -> Dict[str, object]:
        if not rows:
            return {"accuracy": 0.0, "per_intent": {}, "calibration": []}

        totals: Counter[str] = Counter()
        predicted: Counter[str] = Counter()
        correct_by_intent: Counter[str] = Counter()
        correct = 0
        buckets = [{"low": index / 5, "high": (index + 1) / 5, "total": 0, "correct": 0} for index in range(5)]

        for row in rows:
            result = self.predict(row["command"])
            gold = row["intent"]
            guess = str(result["intent"])
            confidence = float(result["confidence"])
            totals[gold] += 1
            predicted[guess] += 1
            is_correct = guess == gold
            if is_correct:
                correct += 1
                correct_by_intent[gold] += 1
            bucket_index = min(4, max(0, int(confidence * 5)))
            buckets[bucket_index]["total"] += 1
            buckets[bucket_index]["correct"] += int(is_correct)

        per_intent = {}
        for label in sorted(totals):
            precision = correct_by_intent[label] / predicted[label] if predicted[label] else 0.0
            recall = correct_by_intent[label] / totals[label] if totals[label] else 0.0
            per_intent[label] = {"precision": round(precision, 4), "recall": round(recall, 4), "support": totals[label]}

        calibration = []
        for bucket in buckets:
            total = bucket["total"]
            calibration.append(
                {
                    "range": f"{bucket['low']:.1f}-{bucket['high']:.1f}",
                    "count": total,
                    "accuracy": round(bucket["correct"] / total, 4) if total else 0.0,
                }
            )
        return {"accuracy": round(correct / len(rows), 4), "per_intent": per_intent, "calibration": calibration}

    def _fit_vectors(self, rows: Sequence[Dict[str, str]], use_embeddings: bool) -> List[List[float]]:
        # Embeddings are supported, but a full corpus pass can be expensive on
        # the target machine. Large datasets use the deterministic fallback
        # unless callers explicitly pass a smaller fixture.
        if use_embeddings and len(rows) <= 300 and self._embedding_available():
            vectors = [embed(row["command"], host=self.host, model=self.embedding_model, timeout=3.0) for row in rows]
            if all(vector for vector in vectors):
                self.feature_type = "embeddings"
                self.vocab = {}
                return [_normalise(vector or []) for vector in vectors]

        self.feature_type = "char_ngrams"
        counts: Counter[str] = Counter()
        for row in rows:
            counts.update(_ngrams(row["command"]))
        self.vocab = {token: index for index, (token, _) in enumerate(counts.most_common(self.max_features))}
        return [self._char_vector(row["command"]) for row in rows]

    def _embedding_available(self) -> bool:
        try:
            vector = embed("intent classifier probe", host=self.host, model=self.embedding_model, timeout=2.0, keep_alive="0s")
            return bool(vector)
        except Exception:
            return False

    def _vectorise(self, command: str) -> List[float]:
        if self.feature_type == "embeddings":
            vector = embed(command, host=self.host, model=self.embedding_model, timeout=3.0)
            if vector:
                return _normalise(vector)
        return self._char_vector(command)

    def _char_vector(self, command: str) -> List[float]:
        vector = [0.0 for _ in range(len(self.vocab))]
        for token in _ngrams(command):
            index = self.vocab.get(token)
            if index is not None:
                vector[index] += 1.0
        return _normalise(vector)

    @staticmethod
    def _confidence(scores: Sequence[float]) -> float:
        if not scores:
            return 0.0
        shifted = [math.exp(max(-20.0, min(20.0, score * 8.0))) for score in scores]
        total = sum(shifted)
        if total == 0.0:
            return 0.0
        return round(max(0.0, min(1.0, shifted[0] / total)), 4)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the learned ASC intent classifier.")
    parser.add_argument("--corpus", default=str(CORPUS_PATH))
    parser.add_argument("--model", default=str(MODEL_PATH))
    parser.add_argument("--no-embeddings", action="store_true", help="Force the char n-gram fallback backend.")
    args = parser.parse_args()

    start = time.perf_counter()
    classifier = IntentClassifier(model_path=args.model)
    metrics = classifier.train(args.corpus, use_embeddings=not args.no_embeddings)
    classifier.save()
    elapsed = time.perf_counter() - start

    print(json.dumps(metrics, indent=2, sort_keys=True))
    print(f"Saved classifier to {classifier.model_path}")
    print(f"Training completed in {elapsed:.2f}s on CPU-friendly features.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
