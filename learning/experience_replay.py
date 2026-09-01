"""
Experience replay utilities for ASC learning and command history.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


class ExperienceReplayBuffer:
    """Persistent ring buffer for command execution experiences.

    Backed by SQLite (data/episodic_memory.db - the same file MemorySystem
    uses for episodes/tasks) instead of a whole-file JSON rewrite on every
    single command. The previous JSON version rewrote the entire history
    (271KB+ once the buffer filled up) from scratch on every command; this
    is now an O(1) insert plus a bounded delete for the ring-buffer cap.

    Keeps the exact same add()/recent()/all() interface and return shape
    (a list of the same experience dicts) as the JSON version, so
    LearningAgent/AdaptiveLearningEngine/OfflinePreferenceModel/
    NeuralCommandModel - all of which call replay.all() - need no changes.

    A pre-existing command_history.json (from before this migration) is
    imported once on first use and then left on disk untouched as a backup;
    nothing is deleted.
    """

    def __init__(self, path: str, capacity: int = 500):
        self.json_path = Path(path)
        self.path = self.json_path  # backward-compat alias for external readers
        self.capacity = capacity
        self.db_path = self.json_path.parent / "episodic_memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Optional[List[Dict[str, Any]]] = None
        self._init_db()
        self._migrate_json_if_needed()

    def _connect(self) -> sqlite3.Connection:
        # Busy timeout: this DB is shared with MemorySystem and the
        # background workers, so wait briefly on contention rather than
        # failing immediately with "database is locked".
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _init_db(self):
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS command_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                intent_type TEXT,
                data TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_command_history_intent ON command_history(intent_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_command_history_timestamp ON command_history(timestamp)")
        conn.commit()
        conn.close()

    def _migrate_json_if_needed(self):
        """One-time import of a pre-existing JSON history file."""
        if not self.json_path.exists():
            return
        conn = self._connect()
        existing = conn.execute("SELECT COUNT(*) FROM command_history").fetchone()[0]
        conn.close()
        if existing > 0:
            return  # already migrated, or genuinely has data - never overwrite

        try:
            old_experiences = json.loads(self.json_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(old_experiences, list) or not old_experiences:
            return

        conn = self._connect()
        for exp in old_experiences[-self.capacity:]:
            if not isinstance(exp, dict):
                continue
            conn.execute(
                "INSERT INTO command_history (timestamp, intent_type, data) VALUES (?, ?, ?)",
                (
                    exp.get("timestamp"),
                    exp.get("intent_type") or ((exp.get("strategy") or {}).get("intent") or {}).get("type"),
                    json.dumps(exp, default=str),
                ),
            )
        conn.commit()
        conn.close()

    def add(self, experience: Dict[str, Any]):
        conn = self._connect()
        conn.execute(
            "INSERT INTO command_history (timestamp, intent_type, data) VALUES (?, ?, ?)",
            (
                experience.get("timestamp"),
                experience.get("intent_type"),
                json.dumps(experience, default=str),
            ),
        )
        # Ring-buffer cap: drop rows beyond capacity, oldest first.
        conn.execute(
            "DELETE FROM command_history WHERE id NOT IN "
            "(SELECT id FROM command_history ORDER BY id DESC LIMIT ?)",
            (self.capacity,),
        )
        conn.commit()
        conn.close()
        self._cache = None  # history changed - next all() re-reads

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        conn = self._connect()
        rows = conn.execute(
            "SELECT data FROM command_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [json.loads(row[0]) for row in reversed(rows)]

    def all(self) -> List[Dict[str, Any]]:
        """Every stored experience, oldest first.

        Cached until the next add(). Routing calls this 5-8 times per command
        (find_similar_success, discover_workflow_patterns, get_intent_
        confidence up to 3x, plus both model refreshes) and each uncached
        call re-read and re-parsed all 500 rows - roughly 50-80ms of
        duplicated work per command. The buffer only changes via add(), so
        invalidating there keeps this exact.
        """
        if self._cache is None:
            conn = self._connect()
            rows = conn.execute("SELECT data FROM command_history ORDER BY id ASC").fetchall()
            conn.close()
            self._cache = [json.loads(row[0]) for row in rows]
        # Copy so a caller mutating the list can't corrupt the cache.
        return list(self._cache)
