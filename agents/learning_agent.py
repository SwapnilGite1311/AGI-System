"""
Learning Agent - command history, successful pattern reuse, and form memory.
"""

import json
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from learning.adaptive_engine import AdaptiveLearningEngine
from learning.experience_replay import ExperienceReplayBuffer
from learning.phase5_model import OfflinePreferenceModel
from learning.reward_model import RewardModel

from core.config import load_config


class LearningAgent:
    """Tracks execution history and reusable interaction patterns."""

    REFRESH_INTERVAL = 300.0  # seconds between expensive model retrains

    def __init__(self, config_path: str = "./config/settings.json"):
        self.project_root = Path(config_path).resolve().parent.parent
        self._last_model_refresh = 0.0

        self.config = load_config(config_path)
        data_path = self._resolve_project_path(self.config["paths"]["data"])
        data_path.mkdir(parents=True, exist_ok=True)

        learning_config = self.config.get("learning", {})
        history_limit = int(learning_config.get("history_limit", 500))

        self.replay = ExperienceReplayBuffer(
            path=str(data_path / "command_history.json"),
            capacity=history_limit,
        )
        self.reward_model = RewardModel()
        self.form_patterns_path = data_path / "form_patterns.json"
        self.form_patterns = self._load_form_patterns()
        self.feedback_path = data_path / "feedback.json"
        self.feedback_items = self._load_json_dict(self.feedback_path)
        self.adaptive_engine = AdaptiveLearningEngine(
            path=str(data_path / "adaptive_state.json"),
            min_recommendation_score=float(learning_config.get("adaptive_min_confidence", 0.82)),
        )
        # Two different decisions were sharing one threshold. Replaying a
        # past STRATEGY wholesale is consequential and should stay strict at
        # 0.82; the neural ROUTE prediction is advisory - it never bypasses a
        # safety check, and being wrong costs a slower path rather than an
        # unsafe action. Measured on 65 held-out phrasings, the shared 0.82
        # refused 16 predictions of which 10 were CORRECT; at 0.40 accuracy
        # rises from 66.2% to 81.5%.
        self.phase5_model = OfflinePreferenceModel(
            path=str(data_path / "phase5_model.json"),
            min_confidence=float(
                learning_config.get(
                    "route_min_confidence",
                    learning_config.get("adaptive_min_confidence", 0.82),
                )
            ),
        )

        logger.info("Learning Agent initialized")

    def _resolve_project_path(self, path_value: str) -> Path:
        path = Path(path_value)
        if path.is_absolute():
            return path
        return self.project_root / path

    def _load_form_patterns(self) -> Dict[str, Any]:
        return self._load_json_dict(self.form_patterns_path)

    def _load_json_dict(self, path: Path) -> Dict[str, Any]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_form_patterns(self):
        self.form_patterns_path.write_text(
            json.dumps(self.form_patterns, indent=2),
            encoding="utf-8",
        )

    def record_command(self, command: str, strategy: Dict[str, Any], result: Dict[str, Any]):
        reward = self.reward_model.score_execution(result)
        verification = result.get("verification")
        verified_success = None
        if isinstance(verification, dict) and verification.get("verified"):
            # Real model-checked outcome, not just "every step returned
            # success=True" - this is what get_intent_confidence prefers
            # when scoring whether a route is actually worth reusing.
            verified_success = bool(verification.get("satisfied"))
        experience = {
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "normalized": self._normalize(command),
            "strategy": strategy,
            "intent_type": (strategy.get("intent") or {}).get("type"),
            "result": {
                "success": result.get("success", False),
                "verified_success": verified_success,
                "tier": result.get("tier"),
                "steps_completed": result.get("steps_completed"),
                "steps_total": result.get("steps_total"),
            },
            "reward": reward,
            "recommended": bool(strategy.get("adaptive") or strategy.get("source") == "adaptive_learning"),
            "recommendation_confidence": float(
                strategy.get("adaptive", {}).get("confidence", 0.0)
            ) if isinstance(strategy.get("adaptive"), dict) else 0.0,
        }
        self.replay.add(experience)

        # Throttle expensive model refreshes: they retrain over the full
        # experience buffer and cost 15-35s on CPU-bound machines. Once per
        # REFRESH_INTERVAL seconds is plenty for offline learning.
        now = time.time()
        if now - getattr(self, "_last_model_refresh", 0.0) >= self.REFRESH_INTERVAL:
            self._last_model_refresh = now
            self._refresh_adaptive_state()
            self._refresh_phase5_state()
        return experience

    def get_recent_commands(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.replay.recent(limit)

    def get_learning_stats(self) -> Dict[str, Any]:
        experiences = self.replay.all()
        success_count = sum(1 for item in experiences if item.get("result", {}).get("success"))
        total = len(experiences)

        return {
            "history_count": total,
            "success_rate": round(success_count / total, 2) if total else 0.0,
            "form_patterns": len(self.form_patterns),
            "feedback_count": len(self.feedback_items),
            "workflow_patterns": len(self.discover_workflow_patterns()),
            "adaptive": self.adaptive_engine.state.get("summary", {}),
        }

    def find_similar_success(self, command: str, threshold: float = 0.75) -> Optional[Dict[str, Any]]:
        normalized = self._normalize(command)
        best_match = None
        best_score = 0.0

        for item in self.replay.all():
            if not item.get("result", {}).get("success"):
                continue

            score = SequenceMatcher(None, normalized, item.get("normalized", "")).ratio()
            if score >= threshold and score > best_score:
                best_score = score
                best_match = item

        if best_match:
            return {"match": best_match, "score": round(best_score, 2)}
        return None

    def get_intent_confidence(self, intent_type: str) -> Dict[str, Any]:
        """Real success rate for one intent type, from actual history.

        Prefers the verified outcome (core.council.verify_outcome, threaded
        through record_command as result.verified_success) over the
        structural success flag when both exist for an experience - a step
        that ran without error but didn't satisfy the request should count
        against the route's confidence, not for it. Falls back to the
        structural flag for experiences recorded before verification
        existed, or for tiers verification never ran on.
        """
        samples = 0
        successes = 0
        for item in self.replay.all():
            if item.get("intent_type") != intent_type:
                continue
            result = item.get("result", {})
            verified = result.get("verified_success")
            outcome = verified if verified is not None else result.get("success", False)
            samples += 1
            if outcome:
                successes += 1

        return {
            "samples": samples,
            "successes": successes,
            "success_rate": round(successes / samples, 3) if samples else 0.0,
        }

    def remember_form_pattern(self, form_signature: str, field_order: List[str], metadata: Dict[str, Any] = None):
        self.form_patterns[form_signature] = {
            "field_order": field_order,
            "updated_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        self._save_form_patterns()

    def recall_form_pattern(self, form_signature: str) -> Optional[Dict[str, Any]]:
        return self.form_patterns.get(form_signature)

    def record_feedback(self, feedback: str, sentiment: str = "neutral", command: str = None) -> Dict[str, Any]:
        key = datetime.now().isoformat()
        item = {
            "timestamp": key,
            "feedback": feedback,
            "sentiment": sentiment,
            "command": command,
        }
        self.feedback_items[key] = item
        self.feedback_path.write_text(json.dumps(self.feedback_items, indent=2), encoding="utf-8")
        self._refresh_adaptive_state()
        self._refresh_phase5_state()
        return item

    def refresh_adaptive_state(self, preferences: Dict[str, Any] = None) -> Dict[str, Any]:
        """Public hook to rebuild Phase 4 adaptive learning state."""
        return self._refresh_adaptive_state(preferences=preferences)

    def recommend_strategy(self, command: str) -> Optional[Dict[str, Any]]:
        """Return a safe advisory strategy recommendation for a command."""
        if not self.adaptive_engine.state:
            self._refresh_adaptive_state()
        return self.adaptive_engine.recommend_strategy(command)

    def get_adaptive_summary(self) -> Dict[str, Any]:
        """Expose Phase 4 learning state in a compact, inspectable shape."""
        if not self.adaptive_engine.state:
            self._refresh_adaptive_state()
        return self.adaptive_engine.state

    def classify_command(self, command: str) -> Dict[str, Any]:
        """Expose local adaptive classification for command intent."""
        if not self.adaptive_engine.state:
            self._refresh_adaptive_state()
        return self.adaptive_engine.classify_command(command)

    def get_phase5_summary(self) -> Dict[str, Any]:
        """Expose the offline Phase 5 model summary and advisory predictions."""
        if not self.phase5_model.state:
            self._refresh_phase5_state()
        summary = dict(self.phase5_model.state.get("summary", {}))
        summary.setdefault("preference_model", "offline_preference_model")
        return {
            "summary": summary,
            "clusters": self.phase5_model.state.get("clusters", []),
            "preference_candidates": self.phase5_model.state.get("preference_candidates", []),
            "prediction": self.phase5_model.state.get("prediction", {}),
            "neural_command_model": self.phase5_model.state.get("neural_command_model", {}),
            "offline": True,
            "advisory": True,
        }

    def predict_phase5_preference(self, command: str, preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return a safe advisory preference prediction from the offline model."""
        if not self.phase5_model.state:
            self._refresh_phase5_state(preferences=preferences)
        return self.phase5_model.predict_preference(command, preferences=preferences)

    def learn_explicit_preference(self, key: str, value: Any) -> Dict[str, Any]:
        """Explicitly learn a user preference, updating neural model weights and clusters."""
        preferences = {key: value}
        self._refresh_adaptive_state(preferences=preferences)
        self._refresh_phase5_state(preferences=preferences)
        logger.info("Explicit preference learned and models retrained: {} = {}", key, value)
        return {
            "success": True,
            "learned_preference": {key: value},
            "phase5_summary": self.get_phase5_summary().get("summary", {})
        }

    def discover_workflow_patterns(self, min_count: int = 2) -> List[Dict[str, Any]]:
        groups: Dict[str, Dict[str, Any]] = {}
        for item in self.replay.all():
            normalized = item.get("normalized", "")
            strategy = item.get("strategy", {})
            result = item.get("result", {})
            if not result.get("success"):
                continue

            signature = self._workflow_signature(normalized, strategy)
            if not signature:
                continue

            group = groups.setdefault(signature, {
                "signature": signature,
                "count": 0,
                "examples": [],
                "last_strategy": strategy,
            })
            group["count"] += 1
            if len(group["examples"]) < 3:
                group["examples"].append(item.get("command"))

        return [group for group in groups.values() if group["count"] >= min_count]

    def _workflow_signature(self, normalized: str, strategy: Dict[str, Any]) -> Optional[str]:
        intent_type = (strategy.get("intent") or {}).get("type")
        if intent_type:
            return f"intent:{intent_type}"
        if "search" in normalized and ("amazon" in normalized or "youtube" in normalized):
            return "workflow:site_search"
        if "create" in normalized and ("file" in normalized or "note" in normalized):
            return "workflow:create_note_or_file"
        if "system" in normalized or "process" in normalized:
            return "workflow:system_inspection"
        return None

    def _refresh_adaptive_state(self, preferences: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            return self.adaptive_engine.update(
                self.replay.all(),
                self.feedback_items,
                preferences=preferences or {},
            )
        except Exception as exc:
            logger.warning("Adaptive learning refresh failed without blocking execution: {}", str(exc))
            return self.adaptive_engine.state

    def _refresh_phase5_state(self, preferences: Dict[str, Any] = None) -> Dict[str, Any]:
        # Central throttle: full retraining costs 10-16s on CPU machines.
        # Explicit preference updates force an immediate refresh.
        now = time.time()
        if preferences is None and now - getattr(self, "_last_p5_refresh", 0.0) < self.REFRESH_INTERVAL:
            return self.phase5_model.state
        self._last_p5_refresh = now
        try:
            return self.phase5_model.fit(
                self.replay.all(),
                preferences=preferences or {},
            )
        except Exception as exc:
            logger.warning("Phase 5 model refresh failed without blocking execution: {}", str(exc))
            return self.phase5_model.state

    def _normalize(self, command: str) -> str:
        return " ".join(command.lower().strip().split())
