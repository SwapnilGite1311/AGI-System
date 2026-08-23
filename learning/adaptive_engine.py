"""
Phase 4 adaptive learning utilities.

This module keeps learning advisory and auditable. It extracts lightweight
features, builds semi-supervised labels from feedback, and suggests reusable
strategies without bypassing deterministic safety rules.
"""

import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class AdaptiveLearningEngine:
    """Builds safe learning signals from replay history and user feedback."""

    ROUTE_KEYWORDS = {
        "web": {"search", "google", "youtube", "amazon", "flipkart", "website", "browser", "url", "navigate"},
        "file": {"file", "folder", "desktop", "downloads", "documents", "copy", "move", "organize", "backup", "duplicate"},
        "system": {"process", "cpu", "ram", "memory", "disk", "powershell", "cmd", "network", "app", "open", "close"},
        "form": {"form", "fill", "submit", "email", "name", "phone", "field"},
        "conversation": {"hi", "hello", "thanks", "thank", "how", "what"},
    }

    def __init__(self, path: str, min_recommendation_score: float = 0.82):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.min_recommendation_score = min_recommendation_score
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self):
        self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def update(
        self,
        experiences: List[Dict[str, Any]],
        feedback_items: Dict[str, Any],
        preferences: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Rebuild the adaptive state from the latest learning stores."""

        labeled = self.build_labeled_examples(experiences, feedback_items)
        clusters = self.cluster_workflows(experiences)
        route_scores = self._route_scores(experiences)
        preference_signals = self.extract_preference_signals(experiences, feedback_items, preferences or {})
        preference_evaluation = self._evaluate_preference_signals(preference_signals, preferences or {})

        workflow_templates = self.build_workflow_templates(clusters)
        evaluation_metrics = self._evaluate_adaptive_performance(labeled, clusters, preference_signals, preferences or {})

        self.state = {
            "updated_at": datetime.now().isoformat(),
            "labeled_examples": labeled[-200:],
            "workflow_clusters": clusters,
            "workflow_templates": workflow_templates,
            "route_scores": route_scores,
            "preference_signals": preference_signals,
            "preference_evaluation": preference_evaluation,
            "evaluation_metrics": evaluation_metrics,
            "summary": {
                "examples": len(labeled),
                "clusters": len(clusters),
                "positive_labels": sum(1 for item in labeled if item.get("label") == "positive"),
                "negative_labels": sum(1 for item in labeled if item.get("label") == "negative"),
                "neutral_labels": sum(1 for item in labeled if item.get("label") == "neutral"),
                "workflow_templates": len(workflow_templates),
                "preference_suggestions": len(preference_signals.get("suggestions", [])),
                "recommendation_accuracy": evaluation_metrics.get("recommendation_accuracy", 0.0),
                "user_correction_rate": evaluation_metrics.get("user_correction_rate", 0.0),
                "stable_workflow_templates": evaluation_metrics.get("stable_workflow_templates", 0),
            },
        }
        self._save()
        return self.state

    def build_labeled_examples(
        self,
        experiences: List[Dict[str, Any]],
        feedback_items: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Create semi-supervised labels from success/reward plus explicit feedback."""

        feedback_by_command: Dict[str, str] = {}
        for item in feedback_items.values():
            command = self._normalize(item.get("command") or "")
            sentiment = item.get("sentiment", "neutral")
            if command and sentiment in {"positive", "negative"}:
                feedback_by_command[command] = sentiment

        labeled = []
        for exp in experiences:
            normalized = exp.get("normalized") or self._normalize(exp.get("command", ""))
            result = exp.get("result", {})
            reward = float(exp.get("reward", 0.0) or 0.0)
            label = feedback_by_command.get(normalized)
            source = "feedback"

            if not label:
                source = "weak-supervision"
                if result.get("success") and reward >= 0.75:
                    label = "positive"
                elif not result.get("success") or reward <= 0.25:
                    label = "negative"
                else:
                    label = "neutral"

            labeled.append({
                "command": exp.get("command"),
                "normalized": normalized,
                "label": label,
                "label_source": source,
                "features": self.extract_features(exp.get("command", "")),
                "strategy": exp.get("strategy", {}),
                "reward": reward,
                "recommended": bool(exp.get("recommended", False)),
                "recommendation_confidence": float(exp.get("recommendation_confidence", 0.0) or 0.0),
            })
        return labeled

    def cluster_workflows(self, experiences: List[Dict[str, Any]], min_count: int = 2) -> List[Dict[str, Any]]:
        """Cluster repeated workflows by intent/tier and command keywords."""

        groups: Dict[str, Dict[str, Any]] = {}
        for exp in experiences:
            if not exp.get("result", {}).get("success"):
                continue
            signature = self._cluster_signature(exp)
            group = groups.setdefault(signature, {
                "signature": signature,
                "count": 0,
                "examples": [],
                "avg_reward": 0.0,
                "strategy": exp.get("strategy", {}),
            })
            group["count"] += 1
            group["avg_reward"] += float(exp.get("reward", 0.0) or 0.0)
            if len(group["examples"]) < 5:
                group["examples"].append(exp.get("command"))

        clusters = []
        for group in groups.values():
            if group["count"] >= min_count:
                group["avg_reward"] = round(group["avg_reward"] / group["count"], 2)
                clusters.append(group)
        return sorted(clusters, key=lambda item: (item["count"], item["avg_reward"]), reverse=True)

    def build_workflow_templates(self, clusters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create reusable workflow templates from stable clusters."""

        templates = []
        for cluster in clusters:
            templates.append({
                "signature": cluster.get("signature"),
                "count": cluster.get("count"),
                "avg_reward": cluster.get("avg_reward"),
                "strategy": cluster.get("strategy", {}),
                "examples": cluster.get("examples", [])[:3],
                "template_steps": self._template_from_cluster(cluster),
            })
        return templates

    def _template_from_cluster(self, cluster: Dict[str, Any]) -> List[str]:
        signature = cluster.get("signature", "")
        strategy = cluster.get("strategy", {})
        intent_type = (strategy.get("intent") or {}).get("type", "")

        if intent_type == "browser_action":
            return [
                "Open the default browser or configured browser.",
                "Navigate to the requested URL or search query.",
                "Confirm the page loaded successfully.",
            ]

        if intent_type == "system_info":
            return [
                "Gather the requested system information.",
                "Summarize CPU, memory, disk, or network metrics.",
                "Return a concise status report.",
            ]

        if intent_type == "command_history":
            return [
                "Retrieve recent command history.",
                "Filter and summarize the most relevant entries.",
                "Present the results to the user.",
            ]

        if signature.startswith("workflow:"):
            return [
                f"Execute repeated workflow for {signature.split(':', 1)[1]}.",
                "Reuse the last successful sequence of steps.",
                "Verify the outcome and note any deviations.",
            ]

        if signature.startswith("route:"):
            return [
                f"Execute a stable route for {signature.split(':', 1)[1]}.",
                "Follow the most reliable tool path for this workflow.",
                "Confirm the workflow succeeded.",
            ]

        return [
            "Execute the clustered workflow steps in order.",
            "Validate each step against the user goal.",
            "Report whether the workflow completed successfully.",
        ]

    def _evaluate_adaptive_performance(
        self,
        labeled_examples: List[Dict[str, Any]],
        clusters: List[Dict[str, Any]],
        preference_signals: Dict[str, Any],
        preferences: Dict[str, Any],
    ) -> Dict[str, Any]:
        total = len(labeled_examples)
        positive = sum(1 for item in labeled_examples if item.get("label") == "positive")
        negative = sum(1 for item in labeled_examples if item.get("label") == "negative")
        neutral = total - positive - negative
        accuracy = round(positive / max(1, positive + negative), 2) if (positive + negative) else 0.0
        correction_rate = round(negative / max(1, total), 2) if total else 0.0

        recommended_examples = [item for item in labeled_examples if item.get("recommended")]
        recommended_count = len(recommended_examples)
        correct_recommendations = sum(1 for item in recommended_examples if item.get("result", {}).get("success"))
        recommendation_accuracy = round(correct_recommendations / max(1, recommended_count), 2) if recommended_count else 0.0

        suggestions = preference_signals.get("suggestions", [])
        accepted = sum(1 for suggestion in suggestions if preferences.get(suggestion.get("key")) == suggestion.get("value"))
        suggestion_acceptance = round(accepted / max(1, len(suggestions)), 2) if suggestions else 0.0

        stable_templates = len([cluster for cluster in clusters if cluster.get("count", 0) >= 3])

        # Calculate cluster quality metrics
        cluster_quality_scores = []
        for cluster in clusters:
            count = cluster.get("count", 0)
            avg_reward = cluster.get("avg_reward", 0.0)
            quality_score = round(count * 0.3 + avg_reward * 0.7, 2)
            cluster_quality_scores.append(quality_score)
        
        avg_cluster_quality = round(sum(cluster_quality_scores) / len(cluster_quality_scores), 2) if cluster_quality_scores else 0.0

        return {
            "total_examples": total,
            "positive_labels": positive,
            "negative_labels": negative,
            "neutral_labels": neutral,
            "adaptive_label_accuracy": accuracy,
            "user_correction_rate": correction_rate,
            "recommended_count": recommended_count,
            "correct_recommendations": correct_recommendations,
            "recommendation_accuracy": recommendation_accuracy,
            "workflow_templates_available": len(clusters),
            "stable_workflow_templates": stable_templates,
            "suggestion_acceptance_ratio": suggestion_acceptance,
            "avg_cluster_quality": avg_cluster_quality,
            "cluster_quality_distribution": cluster_quality_scores[:5],  # Top 5 cluster qualities
        }

    def recommend_strategy(self, command: str) -> Optional[Dict[str, Any]]:
        """Suggest a reusable strategy when past evidence is strong enough."""

        normalized = self._normalize(command)
        features = self.extract_features(command)
        best = None
        best_score = 0.0

        for cluster in self.state.get("workflow_clusters", []):
            examples = [self._normalize(example or "") for example in cluster.get("examples", [])]
            text_score = max((self._text_similarity(normalized, example) for example in examples), default=0.0)
            route_score = self._route_overlap(features, cluster.get("strategy", {}))
            reward_score = float(cluster.get("avg_reward", 0.0) or 0.0)
            support_score = min(1.0, cluster.get("count", 0) / 5)
            score = round(text_score * 0.45 + route_score * 0.2 + reward_score * 0.25 + support_score * 0.1, 3)
            if score > best_score:
                best = cluster
                best_score = score

        if best and best_score >= self.min_recommendation_score:
            return {
                "recommended": True,
                "confidence": best_score,
                "source": "adaptive_learning",
                "cluster": best,
                "strategy": best.get("strategy", {}),
            }
        return None

    def extract_preference_signals(
        self,
        experiences: List[Dict[str, Any]],
        feedback_items: Dict[str, Any],
        preferences: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Summarize user preference evidence without automatically changing preferences."""

        commands = " ".join(exp.get("normalized", "") for exp in experiences[-100:])
        suggestions = []
        if commands.count("chrome") >= 3 and "default_browser" not in preferences:
            suggestions.append({"key": "default_browser", "value": "chrome", "confidence": 0.7})
        if commands.count("desktop") >= 3 and "notes_folder" not in preferences:
            suggestions.append({"key": "notes_folder", "value": "Desktop", "confidence": 0.55})

        feedback_counts = Counter(item.get("sentiment", "neutral") for item in feedback_items.values())
        return {
            "suggestions": suggestions,
            "feedback_counts": dict(feedback_counts),
        }

    def classify_command(self, command: str) -> Dict[str, Any]:
        """Classify command intent using cluster signatures and keyword overlap."""

        normalized = self._normalize(command)
        features = self.extract_features(command)
        candidate = None
        candidate_score = 0.0

        for cluster in self.state.get("workflow_clusters", []):
            examples = [self._normalize(example or "") for example in cluster.get("examples", [])]
            text_score = max((self._text_similarity(normalized, example) for example in examples), default=0.0)
            route_score = self._route_overlap(features, cluster.get("strategy", {}))
            score = round(text_score * 0.6 + route_score * 0.4, 3)
            if score > candidate_score:
                candidate_score = score
                candidate = cluster

        if candidate and candidate_score >= 0.65:
            return {
                "predicted_intent": (candidate.get("strategy", {}).get("intent") or {}).get("type", candidate.get("signature")),
                "confidence": candidate_score,
                "source": "adaptive_cluster",
                "cluster": candidate,
            }

        detected_routes = sorted(features.get("keyword_hits", {}).keys())
        if detected_routes:
            route = detected_routes[0]
            return {
                "predicted_intent": f"route:{route}",
                "confidence": 0.55,
                "source": "keyword_route",
            }

        return {"predicted_intent": "unknown", "confidence": 0.0, "source": "none"}

    def _evaluate_preference_signals(self, preference_signals: Dict[str, Any], preferences: Dict[str, Any]) -> Dict[str, Any]:
        """Score preference suggestions based on current evidence and existing settings."""

        suggestions = preference_signals.get("suggestions", [])
        accepted = 0
        available = len(suggestions)
        for suggestion in suggestions:
            if preferences.get(suggestion["key"]) == suggestion["value"]:
                accepted += 1

        return {
            "suggestions_available": available,
            "suggestions_accepted": accepted,
            "acceptance_ratio": round(accepted / max(1, available), 2) if available else 0.0,
        }

    def extract_features(self, command: str) -> Dict[str, Any]:
        normalized = self._normalize(command)
        tokens = normalized.split()
        keyword_hits = {
            route: sorted(words.intersection(tokens))
            for route, words in self.ROUTE_KEYWORDS.items()
            if words.intersection(tokens)
        }
        return {
            "tokens": tokens[:30],
            "token_count": len(tokens),
            "keyword_hits": keyword_hits,
            "has_sequence": any(token in normalized for token in [" and ", " then ", " after that "]),
            "has_path": any(marker in command for marker in [":\\", "/", "\\"]),
        }

    def _route_scores(self, experiences: List[Dict[str, Any]]) -> Dict[str, Any]:
        totals: Dict[str, List[float]] = defaultdict(list)
        for exp in experiences:
            strategy = exp.get("strategy", {})
            route = strategy.get("tier") or strategy.get("source") or "unknown"
            totals[route].append(float(exp.get("reward", 0.0) or 0.0))
        return {
            route: {
                "count": len(scores),
                "avg_reward": round(sum(scores) / len(scores), 2) if scores else 0.0,
            }
            for route, scores in totals.items()
        }

    def _cluster_signature(self, exp: Dict[str, Any]) -> str:
        strategy = exp.get("strategy", {})
        intent = (strategy.get("intent") or {}).get("type")
        if intent:
            return f"intent:{intent}"
        tier = strategy.get("tier")
        source = strategy.get("source")
        features = self.extract_features(exp.get("command", ""))
        routes = sorted(features.get("keyword_hits", {}).keys())
        if routes:
            return f"route:{routes[0]}"
        return f"tier:{tier or source or 'unknown'}"

    def _route_overlap(self, features: Dict[str, Any], strategy: Dict[str, Any]) -> float:
        intent = (strategy.get("intent") or {}).get("type", "")
        keyword_hits = features.get("keyword_hits", {})
        if "browser" in intent and "web" in keyword_hits:
            return 1.0
        if "file" in intent and "file" in keyword_hits:
            return 1.0
        if "system" in intent and "system" in keyword_hits:
            return 1.0
        return 0.4 if keyword_hits else 0.0

    def _text_similarity(self, left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        left_terms = set(left.split())
        right_terms = set(right.split())
        overlap = len(left_terms & right_terms) / max(1, len(left_terms | right_terms))
        length_ratio = min(len(left), len(right)) / max(len(left), len(right)) if max(len(left), len(right)) > 0 else 0.0
        return round(overlap * 0.75 + length_ratio * 0.25, 3)

    def _normalize(self, value: str) -> str:
        return " ".join((value or "").lower().strip().split())
