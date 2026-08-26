"""Tests for D-2 reminders loop (task #19). Dev-authored, new file only.

Covers: due-item fires (print+callback), not-yet-due stays silent,
done/pending-status filtering, garbage timestamps ignored, fired items
marked done in the file, and never-refires.
"""

import asyncio
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.reminders import ReminderLoop


def _write(tmp: Path, items) -> None:
    (tmp / "schedules.json").write_text(json.dumps(items), encoding="utf-8")


def _read(tmp: Path):
    return json.loads((tmp / "schedules.json").read_text(encoding="utf-8"))


def _mkitem(rid, title, when_iso, status="pending"):
    return {"id": rid, "title": title, "reminder_time": when_iso, "status": status}


def test_due_item_fires_and_marks_done():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        past = (datetime.now() - timedelta(minutes=5)).isoformat()
        _write(tmp, [_mkitem("r1", "Call mom", past)])
        spoken = []
        loop = ReminderLoop(tmp / "schedules.json", speak=spoken.append)
        buf = io.StringIO()
        with redirect_stdout(buf):
            fired = loop.check_once()
        assert len(fired) == 1 and fired[0]["id"] == "r1"
        assert spoken == ["Reminder: Call mom"]
        assert "REMINDER: Call mom" in buf.getvalue()
        assert _read(tmp)[0]["status"] == "done"
        # never refires
        with redirect_stdout(io.StringIO()):
            assert loop.check_once() == []
        print("PASS test_due_item_fires_and_marks_done")


def test_future_item_silent():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        _write(tmp, [_mkitem("r2", "Later task", future)])
        spoken = []
        loop = ReminderLoop(tmp / "schedules.json", speak=spoken.append)
        with redirect_stdout(io.StringIO()):
            assert loop.check_once() == []
        assert spoken == []
        assert _read(tmp)[0]["status"] == "pending"  # untouched
        print("PASS test_future_item_silent")


def test_status_filtering_and_bad_timestamps():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        past = (datetime.now() - timedelta(minutes=1)).isoformat()
        _write(tmp, [
            _mkitem("r3", "already done", past, status="done"),
            _mkitem("r4", "bad time", "not-a-date"),
            _mkitem("r5", "no time", ""),
            _mkitem("r6", "good one", past),
        ])
        loop = ReminderLoop(tmp / "schedules.json")
        with redirect_stdout(io.StringIO()):
            fired = loop.check_once()
        assert [i["id"] for i in fired] == ["r6"]
        print("PASS test_status_filtering_and_bad_timestamps")


def test_missing_file_ok():
    with tempfile.TemporaryDirectory() as d:
        loop = ReminderLoop(Path(d) / "nope.json")
        assert loop.check_once() == []
    print("PASS test_missing_file_ok")


def test_run_loop_ticks():
    async def inner():
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            past = (datetime.now() - timedelta(seconds=1)).isoformat()
            _write(tmp, [_mkitem("r7", "tick me", past)])
            spoken = []
            loop = ReminderLoop(
                tmp / "schedules.json",
                speak=spoken.append,
                poll_interval=0.2,
            )
            task = asyncio.create_task(loop.run())
            await asyncio.sleep(0.6)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            assert spoken == ["Reminder: tick me"]
    asyncio.run(inner())
    print("PASS test_run_loop_ticks")


if __name__ == "__main__":
    test_due_item_fires_and_marks_done()
    test_future_item_silent()
    test_status_filtering_and_bad_timestamps()
    test_missing_file_ok()
    test_run_loop_ticks()
    print("\nAll 5 reminder tests passed.")
