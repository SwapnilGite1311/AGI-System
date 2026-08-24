"""
Remote task queue - persists commands arriving from outside the laptop
(WhatsApp/SMS gateway, email bridge) so ASC can execute them safely and
the supervisor can see remote activity on-screen.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class RemoteQueue:
    """JSON-file backed FIFO of remote commands with explicit statuses."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Dict[str, Any]]:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []
        return []

    def _save(self, entries: List[Dict[str, Any]]):
        self.path.write_text(json.dumps(entries[-500:], indent=2), encoding="utf-8")

    def enqueue(self, command: str, source: str = "remote", sender: str = "unknown") -> Dict[str, Any]:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "command": command.strip(),
            "source": source,
            "sender": sender,
            "status": "queued",
            "created": datetime.now().isoformat(timespec="seconds"),
            "result_summary": None,
        }
        entries = self._load()
        entries.append(entry)
        self._save(entries)
        return entry

    def next_queued(self) -> Optional[Dict[str, Any]]:
        for entry in self._load():
            if entry.get("status") == "queued":
                return entry
        return None

    def claim_next(self) -> Optional[Dict[str, Any]]:
        """Atomically mark the oldest queued entry as executing and return it."""
        entries = self._load()
        for entry in entries:
            if entry.get("status") == "queued":
                entry["status"] = "executing"
                entry["started"] = datetime.now().isoformat(timespec="seconds")
                self._save(entries)
                return entry
        return None

    def mark_done(self, task_id: str, result_summary: str):
        entries = self._load()
        for entry in entries:
            if entry.get("id") == task_id:
                entry["status"] = "done"
                entry["result_summary"] = str(result_summary)[:300]
                entry["finished"] = datetime.now().isoformat(timespec="seconds")
                break
        self._save(entries)

    def mark_failed(self, task_id: str, error: str):
        entries = self._load()
        for entry in entries:
            if entry.get("id") == task_id:
                entry["status"] = "failed"
                entry["result_summary"] = str(error)[:300]
                entry["finished"] = datetime.now().isoformat(timespec="seconds")
                break
        self._save(entries)

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._load()[-limit:]
