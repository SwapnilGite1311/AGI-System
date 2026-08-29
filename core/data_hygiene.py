"""
Deduplicate and de-junk the operational stores.

Repeated test runs accumulated in the same files the product reads, so the
live system reported 1,026 tasks of which only 27 were distinct ("Task 1"
appeared 176 times), 156 team members that were four people repeated 39
times each, and 573 projects of which 317 were named some variant of "Test
Project".

That is not cosmetic. Every analytic is computed from these files, so the
completion rate, team size and project counts VEGA reports were all wrong,
and a demo of them shows a wall of duplicates.

Nothing here deletes without writing a timestamped backup first, and
`plan()` reports exactly what would change without touching anything.
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from loguru import logger

# Titles that only ever came from a test run.
JUNK_MARKERS = (
    "test task", "test project", "test reminder", "test ", "probe",
    "dummy", "sample task", "asdf", "qwerty", "foo", "bar baz",
    "status test", "lorem ipsum",
)

# Files to clean, and the key holding the list (None = the file IS the list).
TARGETS: Dict[str, str] = {
    "business_tasks.json": "tasks",
    "team_members.json": "",
    "projects.json": "",
}


def _load(path: Path, key: str) -> Tuple[Any, List[Dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if key and isinstance(raw, dict):
        return raw, list(raw.get(key) or [])
    return raw, list(raw if isinstance(raw, list) else [])


def _label(item: Dict[str, Any]) -> str:
    for field in ("title", "name", "project_name", "description"):
        value = item.get(field)
        if value:
            return str(value).strip()
    return ""


# Test fixtures generated unique addresses by appending a random hex suffix
# ("john_b7f93939@example.com"), so 39 copies of the same person each looked
# like a distinct record and survived identity-based dedup.
_GENERATED_EMAIL = re.compile(r"^[a-z]+_[0-9a-f]{6,}@", re.IGNORECASE)


def _is_junk(item: Dict[str, Any]) -> bool:
    label = _label(item).lower()
    if not label:
        return True
    if any(marker in label for marker in JUNK_MARKERS):
        return True
    return bool(_GENERATED_EMAIL.match(str(item.get("email") or "")))


def _identity(item: Dict[str, Any]) -> Tuple:
    """What makes two records 'the same' for dedup purposes.

    Deliberately ignores id and timestamps - the duplicates came from
    re-running the same fixture, so every copy has a fresh uuid.
    """
    return (
        _label(item).lower(),
        str(item.get("email") or "").lower(),
        str(item.get("role") or "").lower(),
        str(item.get("project_id") or ""),
        str(item.get("category") or ""),
    )


def analyse(data_dir: Path) -> Dict[str, Any]:
    """Report what cleanup would do, changing nothing."""
    report: Dict[str, Any] = {"files": {}, "total_removed": 0}

    for filename, key in TARGETS.items():
        path = data_dir / filename
        if not path.exists():
            continue
        try:
            _, items = _load(path, key)
        except Exception as exc:
            report["files"][filename] = {"error": str(exc)}
            continue

        seen = set()
        keep, junk, dupes = [], 0, 0
        for item in items:
            if not isinstance(item, dict):
                continue
            if _is_junk(item):
                junk += 1
                continue
            ident = _identity(item)
            if ident in seen:
                dupes += 1
                continue
            seen.add(ident)
            keep.append(item)

        removed = len(items) - len(keep)
        report["files"][filename] = {
            "before": len(items),
            "after": len(keep),
            "junk_removed": junk,
            "duplicates_removed": dupes,
            "removed": removed,
        }
        report["total_removed"] += removed

    return report


def clean(data_dir: Path, dry_run: bool = True) -> Dict[str, Any]:
    """Apply the cleanup. Always backs up first unless dry_run."""
    report = analyse(data_dir)
    report["dry_run"] = dry_run
    if dry_run:
        return report

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = data_dir / f"backup_before_cleanup_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    report["backup"] = str(backup_dir)

    from core.atomic_io import write_json_atomic

    for filename, key in TARGETS.items():
        path = data_dir / filename
        if not path.exists() or "error" in report["files"].get(filename, {}):
            continue

        shutil.copy2(path, backup_dir / filename)

        raw, items = _load(path, key)
        seen = set()
        keep = []
        for item in items:
            if not isinstance(item, dict) or _is_junk(item):
                continue
            ident = _identity(item)
            if ident in seen:
                continue
            seen.add(ident)
            keep.append(item)

        if key and isinstance(raw, dict):
            raw[key] = keep
            raw["updated_at"] = datetime.now().isoformat()
            write_json_atomic(path, raw)
        else:
            write_json_atomic(path, keep)

        logger.info("Cleaned {}: {} -> {} records", filename, len(items), len(keep))

    return report
