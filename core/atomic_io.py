"""
Atomic JSON writes.

None of ASC's 78+ hand-rolled load/save methods wrote atomically - a plain
`open(path, "w")` followed by `json.dump` truncates the file in place, and
every loader swallows the resulting garbage as an empty/default state on next
boot, silently discarding the store. A simulated interrupt partway through
saving a 453-task file left it unparseable with no backup.

This module is now the single write path for every JSON store in the project
(audit H-3): business tasks/projects/schedules, the security audit trail and
key store, analytics dashboards and reports, workflow and integration state,
the app cache, reminders, and neural-model metadata.

Durability: the payload is written to a temp file in the same directory,
flushed and fsync'd, then moved into place with os.replace - which is atomic
on both POSIX and Windows. A reader therefore sees either the complete old
file or the complete new one, never a half-written one.
"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class FileLock:
    """Cross-process advisory lock via exclusive file creation.

    Originally private to core/remote_queue.py; promoted here because
    schedules.json has the same problem (audit M-1): the reminders loop and
    business_agent both do read-modify-write on it, from different tasks and
    with no shared lock, so a reminder added between the loop's read and its
    write was silently erased.

    Has a retry/backoff and a stale-lock break, so a crashed holder cannot
    deadlock the file forever.
    """

    def __init__(self, path: Path, timeout: float = 5.0):
        self.lock_path = Path(path).with_name(Path(path).name + ".lock")
        self.timeout = timeout

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except FileExistsError:
                if time.time() > deadline:
                    try:
                        os.unlink(self.lock_path)
                    except OSError:
                        pass
                    continue
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        try:
            os.unlink(self.lock_path)
        except OSError:
            pass
        return False


def write_json_atomic(path: Path, data: Any, indent: int = 2) -> None:
    """Write `data` as JSON to `path` atomically (temp file + os.replace)."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, indent=indent, default=str)
            # os.replace is atomic, but without these the new contents may
            # still be sitting in the OS write cache when power is lost -
            # leaving an atomically-renamed but empty file.
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # BaseException, not Exception: Ctrl+C during a save is exactly the
        # case this module exists for, and KeyboardInterrupt/SystemExit are
        # not Exceptions - catching only Exception orphaned a temp file in
        # the data directory on every interrupted write.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
