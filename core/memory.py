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

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Create data directories
        self.data_path = self._resolve_project_path(self.config['paths']['data'])
        self.data_path.mkdir(exist_ok=True)
        
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
        """Save session history to disk"""
        if self.persist_sessions:
            try:
                self.sessions_path.parent.mkdir(parents=True, exist_ok=True)
                self.sessions_path.write_text(json.dumps(self.sessions, indent=2), encoding="utf-8")
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
        """Save user preferences to disk"""
        try:
            self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
            self.preferences_path.write_text(json.dumps(self.preferences, indent=2), encoding="utf-8")
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
        """Load long-term memory from disk"""
        
        if self.long_term_path.exists():
            with open(self.long_term_path, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_long_term(self):
        """Save long-term memory to disk"""
        
        with open(self.long_term_path, 'w') as f:
            json.dump(self.long_term, f, indent=2)
    
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
        
        conn = sqlite3.connect(self.episodic_db)
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
        
        conn.commit()
        conn.close()
    
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
        
        conn = sqlite3.connect(self.episodic_db)
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
        
        conn.commit()
        conn.close()
        
        logger.info("📝 Episode recorded: {} -> {}", task, "success" if success else "failure")
    
    def recall_similar_episodes(self, task: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Find similar past episodes for learning"""
        
        conn = sqlite3.connect(self.episodic_db)
        cursor = conn.cursor()
        
        # Simple keyword match (can be improved with embeddings)
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
        
        logger.debug("🔍 Found {} similar episodes", len(episodes))
        return episodes
    
    def get_success_rate(self, task_pattern: str) -> float:
        """Get success rate for similar tasks"""
        
        conn = sqlite3.connect(self.episodic_db)
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
        
        conn = sqlite3.connect(self.episodic_db)
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
