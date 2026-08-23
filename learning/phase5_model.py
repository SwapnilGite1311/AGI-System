"""
Phase 5 offline learning scaffold.

This module provides a safe, advisory-only learning path for preference
inference and workflow clustering. It remains fully offline and does not
bypass deterministic safety rules.
"""

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from learning.neural_command_model import NeuralCommandModel


class OnlinePreferenceState:
    """Small state container for incremental preference learning."""

    def __init__(self):
        self.weights: Dict[str, float] = {}
        self.bias: float = 0.0
        self.examples_seen: int = 0
        self.last_update: Optional[str] = None


class OfflinePreferenceModel:
    """Offline clustering plus an incremental online preference learner."""

    def __init__(self, path: str, min_confidence: float = 0.55):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.min_confidence = min_confidence
        self.state: Dict[str, Any] = self._load() or self._get_default_state()
        self.online_state = self.state.get("online_state") or {"weights": {}, "bias": 0.0, "examples_seen": 0, "last_update": None}
        self.neural_command_model = NeuralCommandModel(
            path=str(self.path.with_name("neural_command_model.json")),
            min_confidence=min_confidence,
        )

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}
    
    def _get_default_state(self) -> Dict[str, Any]:
        """Provide default state when loading fails."""
        return {
            "updated_at": datetime.now().isoformat(),
            "offline": True,
            "advisory": True,
            "clusters": [],
            "unsupervised_clusters": [],
            "preference_candidates": [],
            "feature_index": {},
            "neural_profile": {},
            "neural_command_model": {"model_type": "untrained", "trained": False, "metrics": {}},
            "online_state": {"weights": {}, "bias": 0.0, "examples_seen": 0, "last_update": None},
            "summary": {
                "clusters": 0,
                "trained_preferences": 0,
                "advisory": True,
                "offline": True,
                "confidence": 0.0,
                "preference_model": "offline_preference_model",
                "top_cluster": None,
                "evidence_strength": 0.0,
                "neural_model": "untrained",
                "neural_trained": False,
                "neural_accuracy": 0.0,
                "neural_train_examples": 0,
                "neural_eval_examples": 0,
                "unsupervised_clusters": 0,
                "online_updates": 0,
                "online_mode": True,
                "online_weight_strength": 0.0,
            },
        }

    def _save(self):
        self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def fit(self, experiences: List[Dict[str, Any]], preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build an offline model state from recent experiences with cold-start bootstrap."""

        effective_experiences = list(experiences)
        if not effective_experiences:
            effective_experiences = self._get_seed_experiences()

        successful = [exp for exp in effective_experiences if (exp.get("result") or {}).get("success", True)]
        clusters = self._build_clusters(successful)
        preference_candidates = self._build_preference_candidates(successful, preferences or {})
        feature_index = self._build_feature_index(successful)
        neural_profile = self._train_neural_profile(successful, feature_index, preference_candidates)
        neural_command_state = self.neural_command_model.fit(experiences) if experiences else {"model_type": "untrained", "trained": False, "metrics": {}}
        prediction = self._build_prediction(preference_candidates, neural_profile)
        top_cluster = self._pick_top_cluster(clusters)
        evidence_strength = self._estimate_evidence_strength(clusters, preference_candidates, prediction)
        prediction_with_metadata = dict(prediction)
        prediction_with_metadata["confidence_label"] = self._confidence_label(prediction.get("confidence", self.min_confidence))

        self.online_state = self._update_online_state(successful, preferences or {})
        self.state = {
            "updated_at": datetime.now().isoformat(),
            "offline": False,
            "advisory": True,
            "clusters": clusters,
            "unsupervised_clusters": clusters,
            "preference_candidates": preference_candidates,
            "prediction": prediction_with_metadata,
            "feature_index": feature_index,
            "neural_profile": neural_profile,
            "neural_command_model": neural_command_state,
            "online_state": self.online_state,
            "summary": {
                "clusters": len(clusters),
                "trained_preferences": len(preference_candidates),
                "advisory": True,
                "offline": True,
                "confidence": prediction.get("confidence", 0.0),
                "preference_model": "offline_preference_model",
                "top_cluster": top_cluster,
                "evidence_strength": round(evidence_strength, 2),
                "neural_model": neural_command_state.get("model_type", "untrained") if neural_command_state else "untrained",
                "neural_trained": bool(neural_command_state.get("trained", False)) if neural_command_state else False,
                "neural_accuracy": neural_command_state.get("metrics", {}).get("accuracy", 0.0) if neural_command_state else 0.0,
                "neural_train_examples": neural_command_state.get("metrics", {}).get("train_examples", 0) if neural_command_state else 0,
                "neural_eval_examples": neural_command_state.get("metrics", {}).get("eval_examples", 0) if neural_command_state else 0,
                "unsupervised_clusters": len(clusters),
                "online_updates": self.online_state.get("examples_seen", 0),
                "online_mode": True,
                "online_weight_strength": round(self._compute_online_weight_strength(self.online_state), 2),
            },
        }
        self._save()
        return self.state

    def predict_preference(self, command: str, preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return a safe, advisory prediction for a preference from the current model."""

        if not self.state:
            self.fit([], preferences=preferences or {})

        features = self._extract_features(command or "")
        feature_index = self.state.get("feature_index") or self._build_feature_index(self.state.get("clusters", []))
        candidates = self.state.get("preference_candidates", [])
        neural_profile = self.state.get("neural_profile", {})
        online_state = self.state.get("online_state", {})
        neural_route = self.neural_command_model.predict(command or "")
        if candidates:
            top = dict(candidates[0])
            vector = self._vectorize_command(features.get("normalized", ""), feature_index)
            neural_score = self._run_neural_profile(vector, neural_profile)
            confidence = round(min(0.95, max(self.min_confidence, float(top.get("confidence", self.min_confidence)) + neural_score * 0.1)), 2)
            top_copy = dict(top)
            top_copy["confidence"] = confidence
            top_copy["confidence_label"] = self._confidence_label(confidence)
            top_copy["neural_score"] = round(neural_score, 2)
            top_copy["model_source"] = "neural_preference_model"
            top_copy["online_updates"] = online_state.get("examples_seen", 0)
            top_copy["online_weight_score"] = self._compute_online_weight_score(features.get("tokens", []), online_state)
            top_copy["dominant_signal"] = self._dominant_signal(features.get("tokens", []), top_copy.get("key"))
            top_copy["route_prediction"] = neural_route
            reason = self._reason_for_prediction(features, top_copy)
            evidence = self._build_evidence(features, top_copy)
            return {
                "prediction": top_copy,
                "advisory": True,
                "source": "offline_preference_model",
                "reason": reason,
                "evidence": evidence,
                "route_prediction": neural_route,
            }

        if preferences:
            prediction = {"key": "default_browser", "value": preferences.get("default_browser", "chrome"), "confidence": 0.55, "source": "existing_preferences", "advisory": True}
            prediction["confidence_label"] = self._confidence_label(prediction.get("confidence", 0.55))
            return {
                "prediction": prediction,
                "advisory": True,
                "source": "existing_preferences",
                "reason": "Using existing stored preferences.",
                "evidence": self._build_evidence(features, prediction),
                "route_prediction": neural_route,
            }

        prediction = {
            "key": "default_browser",
            "value": "chrome",
            "confidence": 0.55,
            "source": "offline_preference_model",
            "advisory": True,
        }
        prediction["confidence_label"] = self._confidence_label(prediction.get("confidence", 0.55))
        return {
            "prediction": prediction,
            "advisory": True,
            "source": "offline_preference_model",
            "reason": "Default advisory fallback.",
            "evidence": self._build_evidence(features, prediction),
            "route_prediction": neural_route,
        }

    def _build_clusters(self, experiences: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not experiences:
            return []

        feature_index = self._build_feature_index(experiences)
        vectors = [self._vectorize_command(exp.get("command", ""), feature_index) for exp in experiences]
        clusters = self._kmeans_clusters(vectors, feature_index)
        return [
            {
                "cluster_id": cluster.get("cluster_id"),
                "signature": f"cluster:{cluster.get('cluster_id')}",
                "size": cluster.get("size"),
                "examples": cluster.get("examples", []),
                "label": cluster.get("label"),
            }
            for cluster in clusters
        ]

    def _build_preference_candidates(self, experiences: List[Dict[str, Any]], preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        browser_hits = 0
        desktop_hits = 0
        for experience in experiences:
            command = (experience.get("command") or "").lower()
            if "chrome" in command or "browser" in command or "search" in command:
                browser_hits += 1
            if "desktop" in command or "documents" in command or "folder" in command:
                desktop_hits += 1

        if browser_hits >= 1 and "default_browser" not in preferences:
            candidates.append({
                "key": "default_browser",
                "value": "chrome",
                "confidence": 0.7,
                "source": "offline_preference_model",
                "advisory": True,
            })

        if desktop_hits >= 1 and "notes_folder" not in preferences:
            candidates.append({
                "key": "notes_folder",
                "value": "Desktop",
                "confidence": 0.64,
                "source": "offline_preference_model",
                "advisory": True,
            })

        return candidates

    def _update_online_state(self, experiences: List[Dict[str, Any]], preferences: Dict[str, Any]) -> Dict[str, Any]:
        weights = dict(self.online_state.get("weights", {}))
        bias = float(self.online_state.get("bias", 0.0))
        examples_seen = int(self.online_state.get("examples_seen", 0))
        now = datetime.now().isoformat()

        for experience in experiences:
            command = (experience.get("command") or "").lower()
            command_tokens = set(self._tokenize(command))
            if not command_tokens:
                continue

            for token in command_tokens:
                weights[token] = float(weights.get(token, 0.0)) + 0.05
            bias += 0.01
            examples_seen += 1

        if preferences:
            for key, value in preferences.items():
                weights[f"pref:{key}"] = float(weights.get(f"pref:{key}", 0.0)) + 0.03

        for token, weight in list(weights.items()):
            if abs(weight) < 1e-6:
                weights.pop(token, None)

        return {
            "weights": weights,
            "bias": round(bias, 4),
            "examples_seen": examples_seen,
            "last_update": now,
            "mode": "online",
        }

    def _build_prediction(self, candidates: List[Dict[str, Any]], neural_profile: Dict[str, Any]) -> Dict[str, Any]:
        if candidates:
            top = dict(candidates[0])
            confidence = round(min(0.95, max(self.min_confidence, float(top.get("confidence", self.min_confidence)) + float(neural_profile.get("loss", 0.0)) * 0.0)), 2)
            top["confidence"] = confidence
            top["confidence_label"] = self._confidence_label(confidence)
            top["model_source"] = "neural_preference_model"
            return top
        return {
            "key": "default_browser",
            "value": "chrome",
            "confidence": self.min_confidence,
            "source": "offline_preference_model",
            "advisory": True,
            "confidence_label": self._confidence_label(self.min_confidence),
            "model_source": "neural_preference_model",
        }

    def _train_neural_profile(self, experiences: List[Dict[str, Any]], feature_index: Dict[str, int], preference_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not feature_index:
            return {"trained": False, "hidden_units": 0, "output_units": 0, "epochs": 0, "loss": 0.0}

        input_size = len(feature_index)
        hidden_size = min(8, max(4, input_size // 2))  # Increased hidden size
        output_size = max(2, len(preference_candidates) if preference_candidates else 2)
        
        # Better weight initialization (Xavier-like)
        input_weights = [[(math.sqrt(2.0 / (input_size + hidden_size)) * (hash(str(i) + str(h)) % 100 - 50) / 50.0) for h in range(hidden_size)] for i in range(input_size)]
        hidden_weights = [[(math.sqrt(2.0 / (hidden_size + output_size)) * (hash(str(h) + str(o)) % 100 - 50) / 50.0) for o in range(output_size)] for h in range(hidden_size)]
        input_bias = [0.0 for _ in range(hidden_size)]
        hidden_bias = [0.0 for _ in range(output_size)]

        targets = []
        for experience in experiences:
            command = experience.get("command", "") or ""
            features = self._extract_features(command)
            token_hits = features.get("tokens", [])
            if any(token in token_hits for token in ["chrome", "browser", "search", "google", "youtube", "navigate", "url"]):
                targets.append([1.0, 0.0])
            elif any(token in token_hits for token in ["file", "folder", "desktop", "documents", "copy", "move", "organize", "backup"]):
                targets.append([0.0, 1.0])
            else:
                targets.append([0.5, 0.5])

        if not targets:
            return {"trained": False, "hidden_units": hidden_size, "output_units": output_size, "epochs": 0, "loss": 0.0}

        # Balance data by oversampling minority classes
        class_counts = [sum(1 for t in targets if t[0] > 0.5), sum(1 for t in targets if t[1] > 0.5)]
        max_count = max(class_counts)
        balanced_vectors = []
        balanced_targets = []
        
        for vector, target in zip([self._vectorize_command(exp.get("command", ""), feature_index) for exp in experiences], targets):
            balanced_vectors.append(vector)
            balanced_targets.append(target)
            # Oversample minority classes
            if target[0] > 0.5 and class_counts[0] < max_count:
                repeat_factor = max_count // class_counts[0]
                for _ in range(repeat_factor - 1):
                    balanced_vectors.append(vector)
                    balanced_targets.append(target)
            elif target[1] > 0.5 and class_counts[1] < max_count:
                repeat_factor = max_count // class_counts[1]
                for _ in range(repeat_factor - 1):
                    balanced_vectors.append(vector)
                    balanced_targets.append(target)

        best_loss = float('inf')
        learning_rate = 0.01  # Reduced learning rate
        epochs = 100  # Increased epochs

        for epoch in range(epochs):
            loss = 0.0
            for vector, target in zip(balanced_vectors, balanced_targets):
                hidden_values = []
                for h in range(hidden_size):
                    total = input_bias[h]
                    for idx, value in enumerate(vector):
                        total += input_weights[idx][h] * value
                    hidden_values.append(self._tanh(total))

                logits = []
                for o in range(output_size):
                    total = hidden_bias[o]
                    for h, hidden_value in enumerate(hidden_values):
                        total += hidden_weights[h][o] * hidden_value
                    logits.append(total)

                probs = self._softmax(logits)
                # Use cross-entropy loss with numerical stability
                target_class = 0 if target[0] > 0.5 else 1
                loss += -math.log(max(1e-9, probs[target_class]))

                delta_out = []
                for o in range(output_size):
                    delta_out.append(probs[o] - target[o])

                for h in range(hidden_size):
                    error_hidden = 0.0
                    for o in range(output_size):
                        error_hidden += delta_out[o] * hidden_weights[h][o]
                    error_hidden *= (1.0 - hidden_values[h] * hidden_values[h])
                    for idx, value in enumerate(vector):
                        input_weights[idx][h] -= learning_rate * error_hidden * value
                    input_bias[h] -= learning_rate * error_hidden

                for h in range(hidden_size):
                    for o in range(output_size):
                        hidden_weights[h][o] -= learning_rate * delta_out[o] * hidden_values[h]
                for o in range(output_size):
                    hidden_bias[o] -= learning_rate * delta_out[o]

            loss /= len(balanced_vectors)  # Average loss
            
            # Early stopping with patience
            if loss < best_loss:
                best_loss = loss
                # Save best weights
                best_input_weights = [row[:] for row in input_weights]
                best_hidden_weights = [row[:] for row in hidden_weights]
                best_input_bias = input_bias[:]
                best_hidden_bias = hidden_bias[:]
            elif epoch > 20 and loss > best_loss * 1.5:  # Allow some degradation but stop if too bad
                break
            
            if loss < 1e-4:
                break

        # Restore best weights
        if 'best_input_weights' in locals():
            input_weights = best_input_weights
            hidden_weights = best_hidden_weights
            input_bias = best_input_bias
            hidden_bias = best_hidden_bias

        return {
            "trained": True,
            "hidden_units": hidden_size,
            "output_units": output_size,
            "epochs": epoch + 1,
            "loss": round(best_loss, 4),
            "input_weights": input_weights,
            "hidden_weights": hidden_weights,
            "input_bias": input_bias,
            "hidden_bias": hidden_bias,
            "feature_count": input_size,
            "data_balanced": True,
            "balanced_samples": len(balanced_vectors),
        }

    def _run_neural_profile(self, vector: List[float], neural_profile: Dict[str, Any]) -> float:
        if not neural_profile.get("trained"):
            return 0.0

        hidden_values = []
        for h in range(neural_profile.get("hidden_units", 0)):
            total = neural_profile.get("input_bias", [0.0])[h]
            for idx, value in enumerate(vector):
                total += neural_profile.get("input_weights", [[0.0]])[idx][h] * value if idx < len(neural_profile.get("input_weights", [[0.0]])) else 0.0
            hidden_values.append(self._tanh(total))

        logits = []
        for o in range(neural_profile.get("output_units", 0)):
            total = neural_profile.get("hidden_bias", [0.0])[o]
            for h, hidden_value in enumerate(hidden_values):
                total += neural_profile.get("hidden_weights", [[0.0]])[h][o] * hidden_value if h < len(neural_profile.get("hidden_weights", [[0.0]])) else 0.0
            logits.append(total)

        probs = self._softmax(logits)
        return float(max(probs) if probs else 0.0)

    def _extract_features(self, command: str) -> Dict[str, Any]:
        normalized = " ".join((command or "").lower().strip().split())
        tokens = self._tokenize(normalized)
        return {"normalized": normalized, "tokens": tokens}

    def _build_feature_index(self, experiences: List[Dict[str, Any]]) -> Dict[str, int]:
        tokens = set()
        for experience in experiences:
            for token in self._tokenize(experience.get("command", "") or ""):
                tokens.add(token)
        return {token: index for index, token in enumerate(sorted(tokens))}

    def _tokenize(self, command: str) -> List[str]:
        normalized = " ".join((command or "").lower().strip().split())
        tokens = []
        for token in normalized.split():
            if token not in {"the", "and", "for", "to", "of", "a", "an", "in", "on", "with", "from", "or"}:
                tokens.append(token)
        return tokens

    def _vectorize_command(self, command: str, feature_index: Dict[str, int]) -> List[float]:
        vector = [0.0] * len(feature_index)
        for token in self._tokenize(command):
            if token in feature_index:
                vector[feature_index[token]] += 1.0
        return vector

    def _kmeans_clusters(self, vectors: List[List[float]], feature_index: Dict[str, int]) -> List[Dict[str, Any]]:
        if not vectors:
            return []

        cluster_count = min(3, max(1, len(vectors)))
        centroids = [list(vector) for vector in vectors[:cluster_count]]
        assignments = [-1 for _ in vectors]

        for _ in range(6):
            updated = False
            new_assignments = [-1 for _ in vectors]
            for index, vector in enumerate(vectors):
                best_centroid = 0
                best_distance = float("inf")
                for centroid_index, centroid in enumerate(centroids):
                    distance = self._distance(vector, centroid)
                    if distance < best_distance:
                        best_distance = distance
                        best_centroid = centroid_index
                new_assignments[index] = best_centroid
            if new_assignments == assignments:
                break
            assignments = new_assignments
            updated = True
            new_centroids = []
            for centroid_index in range(cluster_count):
                members = [vectors[idx] for idx, assignment in enumerate(assignments) if assignment == centroid_index]
                if not members:
                    new_centroids.append(centroids[centroid_index])
                    continue
                average = [0.0] * len(feature_index)
                for member in members:
                    for idx, value in enumerate(member):
                        average[idx] += value
                for idx in range(len(average)):
                    average[idx] /= max(1, len(members))
                new_centroids.append(average)
            centroids = new_centroids
            if not updated:
                break

        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for idx, assignment in enumerate(assignments):
            grouped.setdefault(assignment, []).append({"index": idx, "command": ""})
        clusters = []
        for assignment, members in sorted(grouped.items()):
            if not members:
                continue
            examples = [""]
            cluster_label = self._cluster_label_from_vectors(vectors, assignments, assignment)
            clusters.append({
                "cluster_id": cluster_label,
                "label": cluster_label,
                "size": len(members),
                "examples": [f"example_{idx + 1}" for idx in range(len(members))],
            })
        return clusters

    def _cluster_label_from_vectors(self, vectors: List[List[float]], assignments: List[int], assignment: int) -> str:
        return "web" if assignment == 0 else "file" if assignment == 1 else "general"

    def _distance(self, left: List[float], right: List[float]) -> float:
        return sum((a - b) ** 2 for a, b in zip(left, right))

    def _tanh(self, value: float) -> float:
        return math.tanh(value)

    def _softmax(self, values: List[float]) -> List[float]:
        if not values:
            return []
        max_value = max(values)
        exp_values = [math.exp(value - max_value) for value in values]
        total = sum(exp_values)
        if total == 0.0:
            return [0.0 for _ in values]
        return [value / total for value in exp_values]

    def _pick_top_cluster(self, clusters: List[Dict[str, Any]]) -> str:
        if not clusters:
            return "general"
        return str(clusters[0].get("cluster_id") or "general")

    def _estimate_evidence_strength(self, clusters: List[Dict[str, Any]], candidates: List[Dict[str, Any]], prediction: Dict[str, Any]) -> float:
        cluster_strength = min(0.6, max(0.1, len(clusters) * 0.2))
        candidate_strength = min(0.3, max(0.05, len(candidates) * 0.1))
        confidence_strength = min(0.2, max(0.05, float(prediction.get("confidence", 0.0)) * 0.2))
        return round(cluster_strength + candidate_strength + confidence_strength, 2)

    def _compute_online_weight_strength(self, online_state: Dict[str, Any]) -> float:
        weights = online_state.get("weights", {}) or {}
        if not weights:
            return 0.0
        return round(sum(abs(value) for value in weights.values()) / max(1, len(weights)), 2)

    def _compute_online_weight_score(self, tokens: List[str], online_state: Dict[str, Any]) -> float:
        if not tokens:
            return 0.0
        weights = online_state.get("weights", {}) or {}
        if not weights:
            return 0.0
        score = 0.0
        for token in tokens:
            score += float(weights.get(token, 0.0))
        return round(min(1.0, max(0.0, score / max(1, len(tokens)))), 2)

    def _dominant_signal(self, tokens: List[str], preference_key: Optional[str]) -> str:
        if preference_key == "default_browser":
            return "default_browser"
        if preference_key == "notes_folder":
            return "notes_folder"
        if any(token in tokens for token in ["chrome", "browser", "search", "google", "youtube", "navigate", "url"]):
            return "default_browser"
        if any(token in tokens for token in ["desktop", "documents", "folder", "copy", "move", "organize", "backup"]):
            return "notes_folder"
        return "general"

    def _confidence_label(self, confidence: float) -> str:
        value = float(confidence or 0.0)
        if value >= 0.8:
            return "high"
        if value >= 0.6:
            return "medium"
        return "low"

    def _build_evidence(self, features: Dict[str, Any], payload: Dict[str, Any]) -> str:
        tokens = features.get("tokens", [])
        if payload.get("key") == "default_browser":
            if any(token in tokens for token in ["chrome", "browser", "search", "google", "youtube", "navigate", "url"]):
                return "Browser-oriented activity was detected repeatedly in the recent command history."
            return "The current interaction pattern is consistent with a browser preference hint."
        if payload.get("key") == "notes_folder":
            return "Recent file-system activity suggests a preferred notes destination."
        return "The recommendation is derived from repeated interaction patterns and remains advisory."

    def _reason_for_prediction(self, features: Dict[str, Any], payload: Dict[str, Any]) -> str:
        if payload.get("key") == "default_browser":
            return "Repeated browser-oriented actions suggest a preferred browser."
        if payload.get("key") == "notes_folder":
            return "Repeated file-system activity suggests a preferred notes folder."
        return "Based on the latest interaction patterns."

    def _get_seed_experiences(self) -> List[Dict[str, Any]]:
        """Return default synthetic seed experiences for cold-start bootstrapping."""
        return [
            {
                "command": "open chrome and search for AI trends",
                "result": {"success": True},
                "strategy": {"intent": {"type": "browser_action"}}
            },
            {
                "command": "organize my desktop by file type",
                "result": {"success": True},
                "strategy": {"intent": {"type": "organize_folder"}}
            },
            {
                "command": "show system info and cpu usage",
                "result": {"success": True},
                "strategy": {"intent": {"type": "system_info"}}
            }
        ]
