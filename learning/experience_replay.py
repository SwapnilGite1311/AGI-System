"""
Experience replay utilities for ASC learning and command history.
"""

import json
from pathlib import Path
from typing import Any, Dict, List


class ExperienceReplayBuffer:
    """Persistent ring buffer for command execution experiences."""

    def __init__(self, path: str, capacity: int = 500):
        self.path = Path(path)
        self.capacity = capacity
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.experiences = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save(self):
        self.path.write_text(json.dumps(self.experiences, indent=2), encoding="utf-8")

    def add(self, experience: Dict[str, Any]):
        self.experiences.append(experience)
        if len(self.experiences) > self.capacity:
            self.experiences = self.experiences[-self.capacity :]
        self._save()

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        return self.experiences[-limit:]

    def all(self) -> List[Dict[str, Any]]:
        return list(self.experiences)
