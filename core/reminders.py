"""Reminder loop (task #19 / D-2).

Background poller that watches data/schedules.json every 30 seconds while
VEGA runs. When a pending reminder's reminder_time passes, it prints the
reminder, speaks it via the provided callback (asc._speak_text), and flips
its status to "done" so it never fires twice.

Design constraints:
  - READ-ONLY on schedules.json except for flipping fired items' status.
    business_agent.py owns normal writes to this file. Rare contention is
    still contention: both writers now go through core.atomic_io.FileLock
    and re-read inside it, because "near zero" was not zero and a reminder
    added mid-sweep was being silently erased.
  - Never raises: every tick is wrapped; a broken tick logs and continues.
    Output encoding in particular must never abort a fire (see _safe_print).
  - No new dependencies.

Usage (wired in main.py behind --reminders flag):
    loop = ReminderLoop(schedules_path, speak=asc._speak_text)
    asyncio.create_task(loop.run())          # inside async context
    # or: await loop.run()
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.atomic_io import FileLock, write_json_atomic

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30


def _safe_print(text: str) -> None:
    """Delegates to core.console so a fire cannot land mid-prompt."""
    try:
        from core.console import safe_print

        safe_print(text)
        return
    except Exception:
        pass
    return _legacy_safe_print(text)


def _legacy_safe_print(text: str) -> None:
    """Print without ever raising on the console's encoding.

    A reminder that cannot be displayed must still fire and still be marked
    done - the display is the least important part of the operation.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(encoding, "replace").decode(encoding, "replace"))


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
            logger.warning(f"Reminders: could not read {self.schedules_path}: {exc}")
            return []

    def _mark_done(self, ids: List[str]) -> None:
        """Flip fired items' status to done. Only rewrites when needed.

        The read and the write happen under a cross-process lock, and the
        file is re-read inside it. Previously this read outside any lock and
        wrote back its own stale copy, so a reminder the user added between
        the read and the write was silently erased (audit M-1) - and the
        write itself could truncate the file if interrupted (audit H-3).
        """
        if not ids:
            return
        try:
            with FileLock(self.schedules_path):
                # Re-read INSIDE the lock: anything written since our sweep
                # started must survive.
                with open(self.schedules_path, "r", encoding="utf-8") as f:
                    items = json.load(f)
                changed = False
                for item in items:
                    if item.get("id") in ids and item.get("status") == "pending":
                        item["status"] = "done"
                        changed = True
                if changed:
                    write_json_atomic(self.schedules_path, items)
        except Exception as exc:
            logger.warning(f"Reminders: could not mark done: {exc}")

    # ------------------------------------------------------------------
    # A reminder more overdue than this missed its moment; firing it on the
    # next startup is noise, not a service.
    STALE_AFTER = timedelta(hours=12)

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
            # Don't announce reminders that went stale while VEGA was closed.
            # A recorded session fired a "Test Reminder" dated two weeks
            # earlier the moment the app started, interrupting the user for
            # something long irrelevant. Retire them silently instead.
            if (now - due_at) > self.STALE_AFTER:
                logger.info(
                    "Retiring stale reminder '{}' ({} overdue)",
                    item.get("title"), now - due_at,
                )
                self._mark_done(rid)
                self.fired_ids.add(rid)
                continue
            title = str(item.get("title") or "Reminder")
            desc = item.get("description")
            line = f"REMINDER: {title}" + (f" - {desc}" if desc else "")
            # No emoji here. When stdout is not a UTF-8 console - redirected
            # to a log file, or running as a scheduled task - printing one
            # raised UnicodeEncodeError before the item was appended to
            # `due` or marked done, so the reminder never fired and retried
            # forever every 30s while run() logged it as a warning (M-2).
            _safe_print(f"\n[REMINDER] {line}")
            if self.speak:
                try:
                    self.speak(f"Reminder: {title}")
                except Exception as exc:
                    logger.warning(f"Reminders: speak failed: {exc}")
            due.append(item)

        if due:
            self.fired_ids.update(i.get("id") for i in due)
            self._mark_done([i.get("id") for i in due])
        return due

    # ------------------------------------------------------------------
    async def run(self) -> None:
        logger.info(
            f"Reminders loop started (every {self.poll_interval}s, watching {self.schedules_path})"
        )
        while True:
            try:
                self.check_once()
            except Exception as exc:
                logger.warning(f"Reminders tick failed: {exc}")
            await asyncio.sleep(self.poll_interval)
