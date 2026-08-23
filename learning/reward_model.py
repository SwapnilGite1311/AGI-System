"""
Simple reward scoring for ASC execution learning.
"""

from typing import Any, Dict


class RewardModel:
    """Scores command executions for lightweight feedback and ranking."""

    def score_execution(self, result: Dict[str, Any]) -> float:
        if not result:
            return 0.0

        if result.get("success"):
            completed = result.get("steps_completed")
            total = result.get("steps_total")
            if completed is not None and total:
                return round(0.6 + 0.4 * (completed / total), 2)
            return 1.0

        completed = result.get("steps_completed", 0)
        total = result.get("steps_total", 0)
        if total:
            return round(completed / total, 2)
        return 0.0
