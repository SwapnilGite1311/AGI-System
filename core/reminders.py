"""Reminder loop (task #19 / D-2).

Background poller that watches data/schedules.json every 30 seconds while
VEGA runs. When a pending reminder's reminder_time passes, it prints the
reminder, speaks it via the provided callback (asc._speak_text), and flips
its status to "done" so it never fires twice.

Design constraints:
  - READ-ONLY on schedules.json except for flipping fired items' status.
    business_agent.py owns normal writes to this file; we only rewrite when
    something actually fires (rare), keeping contention near zero.
  - Never raises: every tick is wrapped; a broken tick logs and continues.
  - No new dependencies.

Usage (wired in main.py behind --reminders flag):
    loop = ReminderLoop(schedules_path, speak=asc._speak_text)
    asyncio.create_task(loop.run())          # inside async context
    # or: await loop.run()
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30


def _parse_time(value: Any) -> Optional[datetime]:
    """Parse a schedule timestamp; returns None on missing/garbage."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class ReminderLoop:
    """Polls schedules.json and fires due reminders (print + speak)."""

    def __init__(
        self,
        schedules_path: Path,
        speak: Optional[Callable[[str], None]] = None,
        poll_interval: int = POLL_INTERVAL_SECONDS,
    ):
        self.schedules_path = Path(schedules_path)
        self.speak = speak
        self.poll_interval = poll_interval
        self.fired_ids: set = set()

    # ------------------------------------------------------------------
    def _load_schedules(self) -> List[Dict[str, Any]]:
        try:
            with open(self.schedules_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except FileNotFoundError:
            return []
        except Exception as exc:
            logger.warning("Reminders: could not read {}: {}", self.schedules_path, exc)
            return []

    def _mark_done(self, ids: List[str]) -> None:
        """Flip fired items' status to done. Only rewrites when needed."""
        if not ids:
            return
        try:
            with open(self.schedules_path, "r", encoding="utf-8") as f:
                items = json.load(f)
            changed = False
            for item in items:
                if item.get("id") in ids and item.get("status") == "pending":
                    item["status"] = "done"
                    changed = True
            if changed:
                with open(self.schedules_path, "w", encoding="utf-8") as f:
                    json.dump(items, f, indent=2)
        except Exception as exc:
            logger.warning("Reminders: could not mark done: {}", exc)

    # ------------------------------------------------------------------
    def check_once(self) -> List[Dict[str, Any]]:
        """Single sweep. Returns the reminders fired this sweep."""
        now = datetime.now()
        due: List[Dict[str, Any]] = []
        for item in self._load_schedules():
            rid = item.get("id")
            if not rid or rid in self.fired_ids:
                continue
            if item.get("status") != "pending":
                continue
            due_at = _parse_time(item.get("reminder_time"))
            if due_at is None or due_at > now:
                continue
            title = str(item.get("title") or "Reminder")
            desc = item.get("description")
            line = f"REMINDER: {title}" + (f" - {desc}" if desc else "")
            print(f"\n⏰ {line}")
            if self.speak:
                try:
                    self.speak(f"Reminder: {title}")
                except Exception as exc:
                    logger.warning("Reminders: speak failed: {}", exc)
            due.append(item)

        if due:
            self.fired_ids.update(i.get("id") for i in due)
            self._mark_done([i.get("id") for i in due])
        return due

    # ------------------------------------------------------------------
    async def run(self) -> None:
        logger.info(
            "Reminders loop started (every {}s, watching {})",
            self.poll_interval,
            self.schedules_path,
        )
        while True:
            try:
                self.check_once()
            except Exception as exc:
                logger.warning("Reminders tick failed: {}", exc)
            await asyncio.sleep(self.poll_interval)
