"""
Memory System - Multi-layer memory for the AGI
- Short-term: Recent context (in-memory dict)
- Long-term: Persistent knowledge (JSON files for now)
- Episodic: Experiences and learnings (SQLite)
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from core.atomic_io import write_json_atomic
from core.embeddings import embed, cosine_similarity, pack_embedding, unpack_embedding

from core.config import load_config


class MemorySystem:
    """
    Three-layer memory architecture:
    1. Short-term: Current session context
    2. Long-term: Persistent facts and knowledge
    3. Episodic: Past experiences and interactions
    """
    
    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize memory system"""

        self.project_root = Path(config_path).resolve().parent.parent

        self.config = load_config(config_path)
        # Create data directories
        self.data_path = self._resolve_project_path(self.config['paths']['data'])
        self.data_path.mkdir(exist_ok=True)

        embeddings_config = self.config.get("embeddings", {})
        self.embedding_model = embeddings_config.get("model", "nomic-embed-text")
        self.embedding_host = self.config.get("ollama", {}).get("host", "http://127.0.0.1:11434")
        
        # Short-term memory (in-memory)
        self.short_term = {}
        self.short_term_limit = 100  # Max items
        
        # Long-term memory (JSON file)
        self.long_term_path = self.data_path / "long_term_memory.json"
        self.long_term = self._load_long_term()
        
        # Episodic memory (SQLite)
        self.episodic_db = self.data_path / "episodic_memory.db"
        self._init_episodic_db()
        
        # Persistent User Sessions & Preferences (Priority 3)
        session_config = self.config.get("session", {})
        self.persist_sessions = session_config.get("persist_sessions", True)
        self.sessions_path = self._resolve_project_path(session_config.get("session_file", "./data/sessions.json"))
        self.preferences_path = self._resolve_project_path(session_config.get("preferences_file", "./data/user_preferences.json"))
        self.max_sessions = int(session_config.get("max_sessions", 50))
        self.auto_prune_days = int(session_config.get("auto_prune_days", 30))
        
        self.current_session_id = None
        self.sessions = self._load_sessions()
        self.preferences = self._load_preferences()
        
        logger.info("🧠 Memory system initialized (enhanced)")
        
    def _connect_db(self) -> sqlite3.Connection:
        """Open the episodic DB with a busy timeout.

        Several writers touch this file - the interactive command path, the
        remote-queue worker, the memory-maintenance worker, and any
        concurrent `--journal`/`--tasks` invocation. WAL makes contention
        unlikely but not impossible; without an explicit timeout a collision
        surfaces as an immediate "database is locked" instead of a short wait.
        """
        conn = sqlite3.connect(self.episodic_db, timeout=10.0)
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _resolve_project_path(self, path_value: str) -> Path:
        """Resolve config paths once so cwd changes cannot break memory."""

        path = Path(path_value)
        if path.is_absolute():
            return path
        return self.project_root / path

    def _load_sessions(self) -> List[Dict[str, Any]]:
        """Load session history from disk"""
        if self.persist_sessions and self.sessions_path.exists():
            try:
                return json.loads(self.sessions_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to load sessions: {}", str(e))
        return []

    def _save_sessions(self):
        """Save session history to disk atomically."""
        if self.persist_sessions:
            try:
                write_json_atomic(self.sessions_path, self.sessions)
            except Exception as e:
                logger.error("Failed to save sessions: {}", str(e))

    def _load_preferences(self) -> Dict[str, Any]:
        """Load user preferences from disk"""
        if self.preferences_path.exists():
            try:
                return json.loads(self.preferences_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to load preferences: {}", str(e))
        return {}

    def _save_preferences(self):
        """Save user preferences to disk atomically."""
        try:
            write_json_atomic(self.preferences_path, self.preferences)
        except Exception as e:
            logger.error("Failed to save preferences: {}", str(e))

    def start_session(self, initial_activity: str = "CLI startup") -> str:
        """Start a new user session and return session ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_session_id = f"session_{timestamp}"
        
        session_entry = {
            "session_id": self.current_session_id,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "activities": [initial_activity]
        }
        
        self.sessions.append(session_entry)
        self.prune_old_sessions()
        self._save_sessions()
        logger.info("Session started: {}", self.current_session_id)
        return self.current_session_id

    def log_session_activity(self, activity: str):
        """Log an activity to the current active session"""
        if not self.current_session_id and self.sessions:
            # Re-attach to the last session if none active
            self.current_session_id = self.sessions[-1]["session_id"]
            
        for sess in self.sessions:
            if sess["session_id"] == self.current_session_id:
                sess["activities"].append(activity)
                self._save_sessions()
                break

    def end_session(self):
        """End the current session and update its end_time"""
        if not self.current_session_id:
            return
            
        for sess in self.sessions:
            if sess["session_id"] == self.current_session_id:
                sess["end_time"] = datetime.now().isoformat()
                self._save_sessions()
                break
                
        logger.info("Session ended: {}", self.current_session_id)
        self.current_session_id = None

    def prune_old_sessions(self):
        """Prune session history older than auto_prune_days or exceeding max_sessions"""
        pruned = False
        now = datetime.now()
        
        # Filter by age
        valid_sessions = []
        for sess in self.sessions:
            try:
                start_dt = datetime.fromisoformat(sess["start_time"])
                if now - start_dt < timedelta(days=self.auto_prune_days):
                    valid_sessions.append(sess)
                else:
                    pruned = True
            except Exception:
                valid_sessions.append(sess)
                
        # Limit total count
        if len(valid_sessions) > self.max_sessions:
            valid_sessions = valid_sessions[-self.max_sessions:]
            pruned = True
            
        if pruned:
            self.sessions = valid_sessions
            self._save_sessions()
            logger.info("Pruned old/excess sessions")

    def save_user_preference(self, key: str, value: Any):
        """Save a persistent user preference"""
        self.preferences[key] = {
            "value": value,
            "updated_at": datetime.now().isoformat()
        }
        self._save_preferences()
        logger.info("Saved preference: {} = {}", key, value)

    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """Recall a persistent user preference"""
        if key in self.preferences:
            return self.preferences[key]["value"]
        return default

    def get_last_session_activities(self, limit: int = 10) -> List[str]:
        """Retrieve recent activities from the last session for context"""
        if not self.sessions:
            return []

        if self.current_session_id:
            for session in reversed(self.sessions):
                if session.get("session_id") == self.current_session_id:
                    return session.get("activities", [])[-limit:]

        target = self.sessions[-1]
        activities = target.get("activities", [])
        return activities[-limit:]
    
    # ============= SHORT-TERM MEMORY =============
    
    def remember_short_term(self, key: str, value: Any, ttl: int = 3600):
        """
        Store in short-term memory (current session)
        
        Args:
            key: Memory key
            value: Value to remember
            ttl: Time to live in seconds (not enforced yet, for future)
        """
        
        # Limit size
        if len(self.short_term) >= self.short_term_limit:
            # Remove oldest
            oldest = next(iter(self.short_term))
            del self.short_term[oldest]
        
        self.short_term[key] = {
            "value": value,
            "timestamp": datetime.now().isoformat(),
            "ttl": ttl
        }
        
        logger.debug("💭 Short-term memory stored: {}", key)
    
    def recall_short_term(self, key: str) -> Optional[Any]:
        """Recall from short-term memory"""
        
        if key in self.short_term:
            return self.short_term[key]["value"]
        return None
    
    def get_recent_context(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent short-term memories for context"""
        
        items = list(self.short_term.items())
        recent = items[-limit:] if len(items) > limit else items
        
        return [
            {"key": k, **v}
            for k, v in recent
        ]
    
    # ============= LONG-TERM MEMORY =============
    
    def _load_long_term(self) -> Dict[str, Any]:
        """Load long-term memory from disk.

        Unlike sessions/preferences, this previously had no exception
        handling and no explicit encoding - invalid JSON or a non-ASCII byte
        (decoded as cp1252 by default on Windows) raised out of __init__ and
        prevented the whole controller from booting.
        """
        if self.long_term_path.exists():
            try:
                return json.loads(self.long_term_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to load long-term memory: {}", str(e))
        return {}

    def _save_long_term(self):
        """Save long-term memory to disk atomically."""
        try:
            write_json_atomic(self.long_term_path, self.long_term)
        except Exception as e:
            logger.error("Failed to save long-term memory: {}", str(e))
    
    def remember_long_term(self, key: str, value: Any, category: str = "general"):
        """
        Store in long-term memory (persists across sessions)
        
        Args:
            key: Memory key
            value: Value to remember
            category: Category for organization
        """
        
        if category not in self.long_term:
            self.long_term[category] = {}
        
        self.long_term[category][key] = {
            "value": value,
            "created": datetime.now().isoformat(),
            "accessed_count": 0
        }
        
        self._save_long_term()
        logger.info("💾 Long-term memory stored: {} -> {}", category, key)
    
    def recall_long_term(self, key: str, category: str = "general") -> Optional[Any]:
        """Recall from long-term memory"""
        
        if category in self.long_term and key in self.long_term[category]:
            memory = self.long_term[category][key]
            memory["accessed_count"] += 1
            memory["last_accessed"] = datetime.now().isoformat()
            self._save_long_term()
            
            return memory["value"]
        
        return None
    
    def search_long_term(self, query: str, category: str = None) -> List[Dict[str, Any]]:
        """Search long-term memory"""
        
        results = []
        categories = [category] if category else self.long_term.keys()
        
        for cat in categories:
            if cat in self.long_term:
                for key, memory in self.long_term[cat].items():
                    if query.lower() in key.lower() or query.lower() in str(memory["value"]).lower():
                        results.append({
                            "category": cat,
                            "key": key,
                            "value": memory["value"],
                            "created": memory["created"]
                        })
        
        return results
    
    # ============= EPISODIC MEMORY =============
    
    def _init_episodic_db(self):
        """Initialize episodic memory database"""

        conn = self._connect_db()
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                task TEXT NOT NULL,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                success INTEGER NOT NULL,
                context TEXT,
                learned TEXT
            )
        """)

        # Durable records for multi-step plans: status/attempts/last error so
        # a crash mid-plan is visible on the next boot instead of vanishing
        # silently (it previously existed only as local variables in one
        # coroutine). Deliberately NOT auto-resumed - see get_incomplete_tasks.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 1,
                steps_completed INTEGER NOT NULL DEFAULT 0,
                steps_total INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            )
        """)

        # Human-reviewable record of every executed command. Previously a
        # single JSON file rewritten whole (up to 500 entries) on every
        # command; now an O(1) insert plus a bounded delete, same as
        # command_history's migration (learning/experience_replay.py).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                command TEXT NOT NULL,
                tier TEXT,
                success INTEGER NOT NULL,
                data TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_timestamp ON execution_journal(timestamp)")
        # episodes was the only hot table without indexes, yet both recall
        # paths and prune_episodes order by it (audit L-4).
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp)")

        # Semantic recall: an embedding per episode, computed lazily. Optional
        # - recall_similar_episodes falls back to the LIKE scan below when no
        # embedding model is pulled or this table is empty (core/embeddings.py
        # never raises, just returns None).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episode_embeddings (
                episode_id INTEGER PRIMARY KEY,
                embedding BLOB NOT NULL
            )
        """)
        # Must come after the CREATE TABLE: indexing a table that does not
        # exist yet fails outright on a fresh database.
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_episode_embeddings_ep "
            "ON episode_embeddings(episode_id)"
        )

        conn.commit()
        conn.close()
        self._migrate_journal_json_if_needed()

    def _migrate_journal_json_if_needed(self):
        """One-time import of a pre-existing execution_journal.json."""
        journal_json_path = self.data_path / "execution_journal.json"
        if not journal_json_path.exists():
            return
        conn = self._connect_db()
        existing = conn.execute("SELECT COUNT(*) FROM execution_journal").fetchone()[0]
        if existing > 0:
            conn.close()
            return  # already migrated, or genuinely has data - never overwrite

        try:
            old_entries = json.loads(journal_json_path.read_text(encoding="utf-8"))
        except Exception:
            conn.close()
            return
        if not isinstance(old_entries, list) or not old_entries:
            conn.close()
            return

        for entry in old_entries[-500:]:
            if not isinstance(entry, dict):
                continue
            conn.execute(
                "INSERT INTO execution_journal (timestamp, command, tier, success, data) VALUES (?, ?, ?, ?, ?)",
                (
                    entry.get("timestamp", ""),
                    str(entry.get("command", ""))[:500],
                    entry.get("tier"),
                    1 if entry.get("success") else 0,
                    json.dumps(entry, default=str),
                ),
            )
        conn.commit()
        conn.close()

    def add_journal_entry(self, entry: Dict[str, Any]):
        """Append one execution-journal entry, keeping only the most recent 500."""
        conn = self._connect_db()
        conn.execute(
            "INSERT INTO execution_journal (timestamp, command, tier, success, data) VALUES (?, ?, ?, ?, ?)",
            (
                entry.get("timestamp", datetime.now().isoformat(timespec="seconds")),
                str(entry.get("command", ""))[:500],
                entry.get("tier"),
                1 if entry.get("success") else 0,
                json.dumps(entry, default=str),
            ),
        )
        conn.execute(
            "DELETE FROM execution_journal WHERE id NOT IN "
            "(SELECT id FROM execution_journal ORDER BY id DESC LIMIT 500)"
        )
        conn.commit()
        conn.close()

    def get_journal_entries(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Return the most recent execution-journal entries, oldest first."""
        conn = self._connect_db()
        rows = conn.execute(
            "SELECT data FROM execution_journal ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [json.loads(row[0]) for row in reversed(rows)]

    def create_task_record(self, command: str, steps_total: int = 0) -> int:
        """Insert a new task record (status 'running') and return its id."""
        now = datetime.now().isoformat()
        conn = self._connect_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (command, status, attempts, steps_total, created, updated) "
            "VALUES (?, 'running', 1, ?, ?, ?)",
            (command, steps_total, now, now),
        )
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return task_id

    def update_task_record(
        self,
        task_id: int,
        status: Optional[str] = None,
        steps_completed: Optional[int] = None,
        steps_total: Optional[int] = None,
        last_error: Optional[str] = None,
    ):
        """Update an existing task record. Only supplied fields change."""
        if task_id is None:
            return
        fields = ["updated = ?"]
        values: List[Any] = [datetime.now().isoformat()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if steps_completed is not None:
            fields.append("steps_completed = ?")
            values.append(steps_completed)
        if steps_total is not None:
            fields.append("steps_total = ?")
            values.append(steps_total)
        if last_error is not None:
            fields.append("last_error = ?")
            values.append(last_error)
        values.append(task_id)

        conn = self._connect_db()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        conn.close()

    def get_incomplete_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return tasks left in a non-terminal state (e.g. by a crash).

        Deliberately not auto-resumed - a multi-step task can have real
        side effects, and resuming one unattended after a crash is exactly
        the kind of default the safety work elsewhere in this codebase
        avoids. This surfaces them for a human to review/re-run.
        """
        conn = self._connect_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, command, status, attempts, steps_completed, steps_total, "
            "last_error, created, updated FROM tasks WHERE status = 'running' "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()
        return rows
    
    def remember_episode(
        self,
        task: str,
        action: str,
        result: str,
        success: bool,
        context: Dict[str, Any] = None,
        learned: str = None
    ):
        """
        Store an episode (experience) in memory
        
        Args:
            task: What was attempted
            action: What was done
            result: What happened
            success: Whether it worked
            context: Additional context
            learned: What was learned from this
        """
        
        conn = self._connect_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO episodes (timestamp, task, action, result, success, context, learned)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            task,
            action,
            result,
            1 if success else 0,
            json.dumps(context) if context else None,
            learned
        ))
        episode_id = cursor.lastrowid

        conn.commit()
        conn.close()

        logger.info("📝 Episode recorded: {} -> {}", task, "success" if success else "failure")

        # Best-effort, never blocks: an unavailable embedding model just
        # means this episode falls back to keyword recall like before.
        try:
            vector = embed(task, host=self.embedding_host, model=self.embedding_model)
            if vector:
                conn = self._connect_db()
                conn.execute(
                    "INSERT OR REPLACE INTO episode_embeddings (episode_id, embedding) VALUES (?, ?)",
                    (episode_id, pack_embedding(vector)),
                )
                conn.commit()
                conn.close()
        except Exception as exc:
            logger.debug("Episode embedding skipped: {}", str(exc))
    
    def recall_similar_episodes(self, task: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Find similar past episodes for learning.

        Tries embedding-based cosine similarity first - understands
        paraphrases a keyword scan misses (e.g. "clean up downloads" vs
        "organize the downloads folder" share no words but are the same
        request). Falls back to the original LIKE '%task%' scan when no
        embedding model is available or no episode has one yet - this was
        always a leading-wildcard scan with no usable index, so the
        fallback path is unchanged, just no longer the only path.
        """
        query_vector = self._embed_query_cached(task)
        if query_vector:
            semantic = self._recall_similar_episodes_semantic(query_vector, limit)
            if semantic:
                return semantic

        return self._recall_similar_episodes_keyword(task, limit)

    def backfill_episode_embeddings(self, batch_limit: int = 200) -> Dict[str, Any]:
        """Embed recent episodes that predate the embeddings table.

        Semantic recall JOINs episodes to episode_embeddings, so episodes
        written before embeddings existed are invisible to it (audit M-1:
        1,079 of 1,100 rows). Runs newest-first in bounded batches so it can
        never turn into an unbounded startup stall; returns how many it did.
        """
        conn = self._connect_db()
        rows = conn.execute(
            "SELECT e.id, e.task FROM episodes e "
            "LEFT JOIN episode_embeddings ee ON ee.episode_id = e.id "
            "WHERE ee.episode_id IS NULL AND e.task IS NOT NULL AND e.task != '' "
            "ORDER BY e.id DESC LIMIT ?",
            (batch_limit,),
        ).fetchall()
        conn.close()

        if not rows:
            return {"embedded": 0, "remaining": 0}

        embedded = 0
        for episode_id, task in rows:
            vector = embed(task, host=self.embedding_host, model=self.embedding_model)
            if not vector:
                break  # model unavailable - stop rather than spin
            conn = self._connect_db()
            conn.execute(
                "INSERT OR REPLACE INTO episode_embeddings (episode_id, embedding) VALUES (?, ?)",
                (episode_id, pack_embedding(vector)),
            )
            conn.commit()
            conn.close()
            embedded += 1

        conn = self._connect_db()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM episodes e LEFT JOIN episode_embeddings ee "
            "ON ee.episode_id = e.id WHERE ee.episode_id IS NULL"
        ).fetchone()[0]
        conn.close()

        if embedded:
            # Background maintenance. Printing it mid-session interrupted the
            # prompt with something the user has no use for.
            logger.debug("Backfilled {} episode embeddings ({} remaining)", embedded, remaining)
        return {"embedded": embedded, "remaining": remaining}

    def prune_episodes(self, keep: int = 2000) -> int:
        """Cap episodic history so it cannot grow without bound (audit M-4).

        command_history and execution_journal were already capped at 500;
        episodes was not, and now carries a ~3KB embedding per row.
        """
        conn = self._connect_db()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM episodes WHERE id NOT IN "
            "(SELECT id FROM episodes ORDER BY id DESC LIMIT ?)", (keep,)
        )
        removed = cursor.rowcount or 0
        # Drop orphaned embeddings for the rows we just removed.
        cursor.execute(
            "DELETE FROM episode_embeddings WHERE episode_id NOT IN (SELECT id FROM episodes)"
        )
        conn.commit()
        conn.close()
        if removed:
            logger.info("Pruned {} old episodes (keeping most recent {})", removed, keep)
        return removed

    # Query-embedding cache. The Ollama round-trip is ~86ms and dominates
    # recall latency; the same phrasings recur constantly within a session
    # (follow-ups, retries, the verification pass re-checking a command).
    _QUERY_CACHE_LIMIT = 128

    def _embed_query_cached(self, task: str) -> Optional[List[float]]:
        """Embed a recall query, reusing a recent identical one."""
        cache = getattr(self, "_query_vector_cache", None)
        if cache is None:
            cache = self._query_vector_cache = {}
        key = (task or "").strip().lower()
        if key in cache:
            return cache[key]

        vector = embed(task, host=self.embedding_host, model=self.embedding_model)
        if vector:
            if len(cache) >= self._QUERY_CACHE_LIMIT:
                cache.pop(next(iter(cache)))  # simple FIFO eviction
            cache[key] = vector
        return vector

    @staticmethod
    def _batch_similarity(query_vector: List[float], vectors: List[List[float]]) -> List[float]:
        """Cosine similarity of one query against many vectors, at once.

        This ran as a Python loop calling cosine_similarity per row - 500
        pure-Python dot products on the Brain tier's critical path (audit
        L-4). numpy is already a dependency; one matrix multiply replaces
        the loop. Falls back to the scalar path if numpy is unavailable so
        recall keeps working rather than failing.
        """
        if not vectors:
            return []
        try:
            import numpy as np

            matrix = np.asarray(vectors, dtype=np.float32)
            query = np.asarray(query_vector, dtype=np.float32)
            norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
            # Guard against a zero vector rather than emitting nan/inf.
            norms[norms == 0] = 1e-9
            return (matrix @ query / norms).tolist()
        except Exception:
            return [cosine_similarity(query_vector, v) for v in vectors]

    def _recall_similar_episodes_semantic(self, query_vector: List[float], limit: int) -> List[Dict[str, Any]]:
        conn = self._connect_db()
        cursor = conn.cursor()
        # Bounded to the most recent 500 embedded episodes rather than an
        # unbounded scan of the whole table's history.
        cursor.execute("""
            SELECT e.id, e.timestamp, e.task, e.action, e.result, e.success, e.context, e.learned, ee.embedding
            FROM episodes e JOIN episode_embeddings ee ON ee.episode_id = e.id
            ORDER BY e.id DESC LIMIT 500
        """)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        row_dicts, vectors = [], []
        for row in rows:
            row_dict = dict(zip(columns, row))
            vectors.append(unpack_embedding(row_dict.pop("embedding")))
            row_dicts.append(row_dict)

        scored = list(zip(self._batch_similarity(query_vector, vectors), row_dicts))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        results = []
        for score, row_dict in scored[:limit]:
            if score < 0.5:  # weak match - not worth returning as "similar"
                continue
            if row_dict.get("context"):
                row_dict["context"] = json.loads(row_dict["context"])
            row_dict["similarity"] = round(score, 3)
            results.append(row_dict)

        logger.debug("🔍 Found {} semantically similar episodes", len(results))
        return results

    def _recall_similar_episodes_keyword(self, task: str, limit: int) -> List[Dict[str, Any]]:
        conn = self._connect_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM episodes
            WHERE task LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (f"%{task}%", limit))

        columns = [desc[0] for desc in cursor.description]
        episodes = []

        for row in cursor.fetchall():
            episode = dict(zip(columns, row))
            if episode['context']:
                episode['context'] = json.loads(episode['context'])
            episodes.append(episode)

        conn.close()

        logger.debug("🔍 Found {} similar episodes (keyword fallback)", len(episodes))
        return episodes
    
    def get_success_rate(self, task_pattern: str) -> float:
        """Get success rate for similar tasks"""
        
        conn = self._connect_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*), SUM(success)
            FROM episodes
            WHERE task LIKE ?
        """, (f"%{task_pattern}%",))
        
        total, successes = cursor.fetchone()
        conn.close()
        
        if total == 0:
            return 0.0
        
        return successes / total
    
    # ============= MEMORY CONSOLIDATION =============
    
    def consolidate_memories(self):
        """
        Move important short-term memories to long-term
        Called periodically (e.g., end of session)
        """
        
        logger.info("🔄 Consolidating memories...")
        
        consolidated = 0
        for key, memory in self.short_term.items():
            # Simple heuristic: if accessed multiple times or important keyword
            # In real system, use AI to decide what's important
            if "important" in key.lower() or "remember" in key.lower():
                self.remember_long_term(key, memory["value"], category="consolidated")
                consolidated += 1
        
        logger.info("Consolidated {} memories to long-term", consolidated)
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory system statistics"""
        
        conn = self._connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM episodes")
        episode_count = cursor.fetchone()[0]
        conn.close()
        
        return {
            "short_term_count": len(self.short_term),
            "long_term_categories": len(self.long_term),
            "long_term_total": sum(len(cat) for cat in self.long_term.values()),
            "episodes_count": episode_count
        }


# Test function
def test_memory():
    """Test memory system"""
    
    memory = MemorySystem()
    
    print("\n=== TEST 1: Short-term Memory ===")
    memory.remember_short_term("current_task", "organizing files")
    memory.remember_short_term("user_mood", "focused")
    print("Recalled:", memory.recall_short_term("current_task"))
    
    print("\n=== TEST 2: Long-term Memory ===")
    memory.remember_long_term("user_name", "Swapnil", category="user_profile")
    memory.remember_long_term("favorite_model", "qwen2.5:14b", category="preferences")
    print("Recalled:", memory.recall_long_term("user_name", "user_profile"))
    
    print("\n=== TEST 3: Episodic Memory ===")
    memory.remember_episode(
        task="organize desktop",
        action="categorized files by type",
        result="desktop organized successfully",
        success=True,
        learned="user prefers folders by file type"
    )
    
    similar = memory.recall_similar_episodes("organize")
    print(f"Found {len(similar)} similar episodes")
    
    print("\n=== Memory Statistics ===")
    print(json.dumps(memory.get_memory_stats(), indent=2))


if __name__ == "__main__":
    test_memory()
# ```

# ---

# ## ✅ FILES COMPLETED:
# ```
# 1. config/settings.json ✅
# 2. core/__init__.py ✅
# 3. core/council.py ✅
# 4. core/chairman.py ✅
# 5. core/memory.py ✅
