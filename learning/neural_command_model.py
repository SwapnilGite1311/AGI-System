"""
Advisory neural command model for Phase 5 learning.

The model is intentionally small and local. It learns from ASC command history
and predicts broad execution routes, but it never bypasses deterministic safety.
"""

import json
import math
import random
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import torch
    import torch.nn as nn
except Exception:  # pragma: no cover - exercised only when torch is unavailable
    torch = None
    nn = None


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "for", "from", "in", "is",
    "it", "me", "my", "of", "on", "or", "please", "the", "then", "there",
    "this", "to", "with", "you",
}


if nn is not None:
    class _CommandRouteNet(nn.Module):
        def __init__(self, input_size: int, hidden_size: int, output_size: int):
            super().__init__()
            self.layers = nn.Sequential(
                nn.Linear(input_size, hidden_size),
                nn.ReLU(),
                nn.Linear(hidden_size, output_size),
            )

        def forward(self, features):
            return self.layers(features)
else:
    _CommandRouteNet = None  # torch unavailable; fallback scorer path is used


class NeuralCommandModel:
    """Train/evaluate a local advisory classifier from command experiences."""

    def __init__(
        self,
        path: str,
        min_examples: int = 6,
        max_features: int = 256,
        min_confidence: float = 0.68,
        seed: int = 42,
        max_epochs: int = 200,
        early_stopping_patience: int = 20,
        learning_rate: float = 0.01,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.min_examples = min_examples
        self.max_features = max_features
        self.min_confidence = min_confidence
        self.seed = seed
        self.max_epochs = max_epochs
        self.early_stopping_patience = early_stopping_patience
        self.learning_rate = learning_rate
        self.state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self):
        self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def fit(self, experiences: List[Dict[str, Any]]) -> Dict[str, Any]:
        examples = self._build_examples(experiences)
        labels = sorted({label for _, label, _ in examples})

        if len(examples) < self.min_examples or len(labels) < 2:
            self.state = self._untrained_state(examples, labels)
            self._save()
            return self.state

        vocabulary = self._build_vocabulary([command for command, _, _ in examples])
        if not vocabulary:
            self.state = self._untrained_state(examples, labels)
            self._save()
            return self.state

        if torch is None or nn is None:
            self.state = self._fit_centroid_model(examples, labels, vocabulary)
            self._save()
            return self.state

        self.state = self._fit_torch_model(examples, labels, vocabulary)
        self._save()
        return self.state

    def predict(self, command: str) -> Dict[str, Any]:
        if not self.state or not self.state.get("trained"):
            return {
                "predicted_route": "unknown",
                "confidence": 0.0,
                "advisory": True,
                "source": "neural_command_model",
                "reason": "Neural model is not trained yet.",
            }

        vocabulary = self.state.get("vocabulary", {})
        labels = self.state.get("labels", [])
        vector = self._vectorize(command, vocabulary)

        if self.state.get("model_type") == "torch_mlp":
            scores = self._predict_torch(vector)
        else:
            scores = self._predict_centroid(vector)

        if not scores:
            return {
                "predicted_route": "unknown",
                "confidence": 0.0,
                "advisory": True,
                "source": "neural_command_model",
                "reason": "No usable scores were produced.",
            }

        best_index = max(range(len(scores)), key=lambda idx: scores[idx])
        confidence = round(float(scores[best_index]), 3)
        predicted = labels[best_index] if best_index < len(labels) else "unknown"

        return {
            "predicted_route": predicted if confidence >= self.min_confidence else "unknown",
            "raw_route": predicted,
            "confidence": confidence,
            "advisory": True,
            "source": "neural_command_model",
            "accepted": confidence >= self.min_confidence,
            "reason": "Prediction is advisory and must pass normal safety checks before execution.",
        }

    def _build_examples(self, experiences: List[Dict[str, Any]]) -> List[Tuple[str, str, float]]:
        examples: List[Tuple[str, str, float]] = []
        for experience in experiences:
            command = (experience.get("command") or "").strip()
            if not command:
                continue

            label = self._label_from_experience(experience)
            if not label:
                continue

            reward = float(experience.get("reward", 0.0) or 0.0)
            success = bool((experience.get("result") or {}).get("success"))
            if not success and reward < 0.4:
                continue
            examples.append((command, label, max(0.2, min(1.0, reward or 0.7))))
        return examples

    def _label_from_experience(self, experience: Dict[str, Any]) -> Optional[str]:
        strategy = experience.get("strategy") or {}
        intent = strategy.get("intent") if isinstance(strategy, dict) else {}
        if not isinstance(intent, dict):
            intent = {}
        intent_type = intent.get("type")

        if intent_type:
            return self._route_from_intent(intent_type)

        normalized = (experience.get("command") or "").lower()
        if any(token in normalized for token in ["chrome", "browser", "search", "google", "youtube", "amazon", "website", "url"]):
            return "web"
        if any(token in normalized for token in ["file", "folder", "note", "desktop", "documents", "backup", "duplicate"]):
            return "file"
        if any(token in normalized for token in ["powershell", "cmd", "system", "process", "network", "drive", "cpu", "ram"]):
            return "system"
        if any(token in normalized for token in ["hi", "hello", "how are", "what can you do"]):
            return "conversation"
        return None

    def _route_from_intent(self, intent_type: str) -> str:
        if intent_type in {"browser_action", "fill_form", "confirm_submission"}:
            return "web"
        if intent_type in {
            "list_files", "search_files", "create_file", "create_folder", "copy_file",
            "move_file", "organize_folder", "file_info", "backup_folder",
            "find_duplicates", "analyze_disk_usage",
        }:
            return "file"
        if intent_type in {
            "system_info", "system_command", "list_processes", "network_info",
            "disk_drives", "environment_variable", "open_application",
            "close_application",
        }:
            return "system"
        if intent_type in {"conversation", "chat"}:
            return "conversation"
        if intent_type in {"show_phase5_learning", "show_adaptive_learning", "show_preferences"}:
            return "learning"
        return "general"

    def _build_vocabulary(self, commands: List[str]) -> Dict[str, int]:
        counts: Counter[str] = Counter()
        for command in commands:
            counts.update(self._tokens(command))
        most_common = counts.most_common(self.max_features)
        return {token: index for index, (token, _) in enumerate(most_common)}

    def _tokens(self, command: str) -> List[str]:
        return [
            token
            for token in re.findall(r"[a-zA-Z0-9_]+", (command or "").lower())
            if token not in STOP_WORDS and len(token) > 1
        ]

    def _vectorize(self, command: str, vocabulary: Dict[str, int]) -> List[float]:
        vector = [0.0] * len(vocabulary)
        tokens = self._tokens(command)
        if not tokens:
            return vector
        for token in tokens:
            if token in vocabulary:
                vector[vocabulary[token]] += 1.0
        length = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / length for value in vector]

    def _untrained_state(self, examples: List[Tuple[str, str, float]], labels: List[str]) -> Dict[str, Any]:
        return {
            "updated_at": datetime.now().isoformat(),
            "trained": False,
            "advisory": True,
            "model_type": "untrained",
            "examples": len(examples),
            "labels": labels,
            "metrics": {
                "train_examples": len(examples),
                "eval_examples": 0,
                "accuracy": 0.0,
                "loss": 0.0,
                "reason": "Need more examples and at least two route labels.",
            },
        }

    def _fit_torch_model(self, examples: List[Tuple[str, str, float]], labels: List[str], vocabulary: Dict[str, int]) -> Dict[str, Any]:
        random.seed(self.seed)
        torch.manual_seed(self.seed)

        label_to_index = {label: index for index, label in enumerate(labels)}
        rows = [(self._vectorize(command, vocabulary), label_to_index[label], weight) for command, label, weight in examples]
        random.shuffle(rows)

        split = max(1, int(len(rows) * 0.8))
        if split >= len(rows):
            split = len(rows) - 1
        train_rows = rows[:split]
        eval_rows = rows[split:]

        x_train = torch.tensor([row[0] for row in train_rows], dtype=torch.float32)
        y_train = torch.tensor([row[1] for row in train_rows], dtype=torch.long)
        sample_weights = torch.tensor([row[2] for row in train_rows], dtype=torch.float32)

        hidden_size = min(64, max(8, len(vocabulary) // 2))
        model = _CommandRouteNet(len(vocabulary), hidden_size, len(labels))
        optimizer = torch.optim.Adam(model.parameters(), lr=self.learning_rate)
        loss_fn = nn.CrossEntropyLoss(reduction="none")

        best_loss = float('inf')
        patience_counter = 0
        last_loss = 0.0
        training_losses = []

        for epoch in range(self.max_epochs):
            optimizer.zero_grad()
            logits = model(x_train)
            losses = loss_fn(logits, y_train)
            loss = (losses * sample_weights).mean()
            loss.backward()
            optimizer.step()
            
            current_loss = float(loss.detach().cpu().item())
            training_losses.append(current_loss)
            
            # Early stopping check
            if current_loss < best_loss:
                best_loss = current_loss
                patience_counter = 0
                # Save best model state
                best_model_state = {key: value.detach().cpu().tolist() for key, value in model.state_dict().items()}
            else:
                patience_counter += 1
                if patience_counter >= self.early_stopping_patience:
                    break
            
            last_loss = current_loss

        # Load best model
        if 'best_model_state' in locals():
            tensors = {key: torch.tensor(value, dtype=torch.float32) for key, value in best_model_state.items()}
            model.load_state_dict(tensors)

        eval_metrics = self._evaluate_torch(model, eval_rows)
        accuracy = eval_metrics["accuracy"]
        weights = {
            key: value.detach().cpu().tolist()
            for key, value in model.state_dict().items()
        }

        return {
            "updated_at": datetime.now().isoformat(),
            "trained": True,
            "advisory": True,
            "model_type": "torch_mlp",
            "vocabulary": vocabulary,
            "labels": labels,
            "hidden_size": hidden_size,
            "weights": weights,
            "metrics": {
                "train_examples": len(train_rows),
                "eval_examples": len(eval_rows),
                "accuracy": accuracy,
                "precision": eval_metrics["precision"],
                "recall": eval_metrics["recall"],
                "f1": eval_metrics["f1"],
                "avg_confidence": eval_metrics["avg_confidence"],
                "loss": round(last_loss, 4),
                "best_loss": round(best_loss, 4),
                "epochs_trained": len(training_losses),
                "min_confidence": self.min_confidence,
                "learning_rate": self.learning_rate,
                "early_stopping_patience": self.early_stopping_patience,
            },
        }

    def _evaluate_torch(self, model: Any, rows: List[Tuple[List[float], int, float]]) -> Dict[str, float]:
        if not rows:
            return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
        
        with torch.no_grad():
            x_eval = torch.tensor([row[0] for row in rows], dtype=torch.float32)
            y_eval = [row[1] for row in rows]
            predictions = torch.argmax(model(x_eval), dim=1).detach().cpu().tolist()
            probabilities = torch.softmax(model(x_eval), dim=1).detach().cpu().tolist()
        
        correct = sum(1 for pred, expected in zip(predictions, y_eval) if pred == expected)
        accuracy = round(correct / len(rows), 3)
        
        # Calculate per-class metrics
        unique_labels = list(set(y_eval))
        precision_scores = []
        recall_scores = []
        
        for label in unique_labels:
            true_positives = sum(1 for pred, exp in zip(predictions, y_eval) if pred == label and exp == label)
            false_positives = sum(1 for pred, exp in zip(predictions, y_eval) if pred == label and exp != label)
            false_negatives = sum(1 for pred, exp in zip(predictions, y_eval) if pred != label and exp == label)
            
            precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
            recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
            
            precision_scores.append(precision)
            recall_scores.append(recall)
        
        avg_precision = round(sum(precision_scores) / len(precision_scores), 3) if precision_scores else 0.0
        avg_recall = round(sum(recall_scores) / len(recall_scores), 3) if recall_scores else 0.0
        f1_score = round(2 * (avg_precision * avg_recall) / (avg_precision + avg_recall), 3) if (avg_precision + avg_recall) > 0 else 0.0
        
        # Calculate average confidence
        avg_confidence = round(sum(max(probs) for probs in probabilities) / len(probabilities), 3) if probabilities else 0.0
        
        return {
            "accuracy": accuracy,
            "precision": avg_precision,
            "recall": avg_recall,
            "f1": f1_score,
            "avg_confidence": avg_confidence,
            "total_samples": len(rows)
        }

    def _predict_torch(self, vector: List[float]) -> List[float]:
        labels = self.state.get("labels", [])
        vocabulary = self.state.get("vocabulary", {})
        if not labels or not vocabulary:
            return []

        model = _CommandRouteNet(len(vocabulary), int(self.state.get("hidden_size", 8)), len(labels))
        tensors = {
            key: torch.tensor(value, dtype=torch.float32)
            for key, value in self.state.get("weights", {}).items()
        }
        model.load_state_dict(tensors)
        model.eval()
        with torch.no_grad():
            logits = model(torch.tensor([vector], dtype=torch.float32))
            probs = torch.softmax(logits, dim=1)[0].detach().cpu().tolist()
        return probs

    def _fit_centroid_model(self, examples: List[Tuple[str, str, float]], labels: List[str], vocabulary: Dict[str, int]) -> Dict[str, Any]:
        grouped: Dict[str, List[List[float]]] = {label: [] for label in labels}
        for command, label, _ in examples:
            grouped[label].append(self._vectorize(command, vocabulary))

        centroids = {}
        for label, vectors in grouped.items():
            if not vectors:
                continue
            centroid = [0.0] * len(vocabulary)
            for vector in vectors:
                for idx, value in enumerate(vector):
                    centroid[idx] += value
            centroids[label] = [value / len(vectors) for value in centroid]

        def _score_against_centroids(vector: List[float]) -> List[float]:
            # Score against the freshly built centroids — self.state may be
            # stale/empty during fit(), so _predict_centroid can't be reused here.
            raw_scores = [max(0.0, self._cosine(vector, centroids.get(label, []))) for label in labels]
            total = sum(raw_scores)
            if total <= 0:
                return [1.0 / len(labels) for _ in labels] if labels else []
            return [score / total for score in raw_scores]

        # Simple centroid evaluation (leave-one-out cross-validation)
        total_correct = 0
        total_samples = 0
        for command, label, _ in examples:
            vector = self._vectorize(command, vocabulary)
            scores = _score_against_centroids(vector)
            best_index = max(range(len(scores)), key=lambda idx: scores[idx])
            predicted = labels[best_index] if best_index < len(labels) else "unknown"
            if predicted == label:
                total_correct += 1
            total_samples += 1
        
        accuracy = round(total_correct / total_samples, 3) if total_samples > 0 else 0.0

        return {
            "updated_at": datetime.now().isoformat(),
            "trained": True,
            "advisory": True,
            "model_type": "centroid_fallback",
            "vocabulary": vocabulary,
            "labels": labels,
            "centroids": centroids,
            "metrics": {
                "train_examples": len(examples),
                "eval_examples": total_samples,
                "accuracy": accuracy,
                "loss": 0.0,
                "reason": "Torch unavailable, using cosine-centroid fallback with leave-one-out evaluation.",
            },
        }

    def _predict_centroid(self, vector: List[float]) -> List[float]:
        labels = self.state.get("labels", [])
        centroids = self.state.get("centroids", {})
        raw_scores = []
        for label in labels:
            raw_scores.append(max(0.0, self._cosine(vector, centroids.get(label, []))))
        total = sum(raw_scores)
        if total <= 0:
            return [1.0 / len(labels) for _ in labels] if labels else []
        return [score / total for score in raw_scores]

    def _cosine(self, left: List[float], right: List[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
        right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
        return numerator / (left_norm * right_norm)
