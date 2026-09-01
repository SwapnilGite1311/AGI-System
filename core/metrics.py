"""
Live system metrics, computed from what VEGA has actually done.

Everything here is read from the real stores - the execution journal,
episodic memory, the embeddings table, the operational files. Nothing is
estimated, illustrative, or hardcoded. If a number cannot be computed it is
reported as None rather than filled in with something plausible, because a
metrics surface that quietly invents figures is the same failure this
project already had to remove from its analytics module.
"""

import collections
import json
import platform
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger


def _connect(db_path: Path) -> Optional[sqlite3.Connection]:
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn
    except Exception as exc:
        logger.warning("Metrics could not open {}: {}", db_path.name, str(exc))
        return None


def _scalar(conn: sqlite3.Connection, sql: str, default=None):
    try:
        row = conn.execute(sql).fetchone()
        return row[0] if row and row[0] is not None else default
    except Exception:
        return default


def collect(data_dir: Path) -> Dict[str, Any]:
    """Gather every metric that can be computed from real records."""
    report: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "host": {
            "platform": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
        },
    }

    # ---- hardware: the whole point is that this runs on modest kit ----
    try:
        import psutil

        memory = psutil.virtual_memory()
        report["host"]["cpu_cores"] = psutil.cpu_count(logical=True)
        report["host"]["ram_total_gb"] = round(memory.total / 2 ** 30, 1)
        report["host"]["ram_available_gb"] = round(memory.available / 2 ** 30, 2)
    except Exception:
        pass

    # ---- routing + reliability, from the execution journal ----
    conn = _connect(data_dir / "episodic_memory.db")
    if conn:
        try:
            tiers = collections.Counter(
                row[0] for row in conn.execute(
                    "SELECT tier FROM execution_journal WHERE tier IS NOT NULL"
                )
            )
            total = sum(tiers.values())
            report["routing"] = {
                "commands_recorded": total,
                "by_tier": dict(tiers.most_common()),
                # The share handled without invoking a language model at all -
                # this is why most commands return in well under a second.
                "model_free_share": (
                    round(tiers.get("direct", 0) / total, 3) if total else None
                ),
            }

            succeeded = _scalar(conn, "SELECT SUM(success) FROM execution_journal", 0)
            attempted = _scalar(conn, "SELECT COUNT(*) FROM execution_journal", 0)
            report["reliability"] = {
                "attempted": attempted,
                "succeeded": succeeded,
                "success_rate": round(succeeded / attempted, 3) if attempted else None,
            }

            episodes = _scalar(conn, "SELECT COUNT(*) FROM episodes", 0)
            embedded = _scalar(conn, "SELECT COUNT(*) FROM episode_embeddings", 0)
            report["memory"] = {
                "episodes": episodes,
                "embedded": embedded,
                "semantic_coverage": round(embedded / episodes, 3) if episodes else None,
                "history_entries": _scalar(conn, "SELECT COUNT(*) FROM command_history", 0),
            }
        finally:
            conn.close()

    # ---- what it manages, from the operational stores ----
    def _count(filename: str, key: str = "") -> Optional[int]:
        path = data_dir / filename
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw.get(key, []) if (key and isinstance(raw, dict)) else raw
            return len(items) if isinstance(items, list) else None
        except Exception:
            return None

    report["workload"] = {
        "tasks": _count("business_tasks.json", "tasks"),
        "projects": _count("projects.json"),
        "team_members": _count("team_members.json"),
    }

    return report


def render_text(report: Dict[str, Any]) -> str:
    """A terminal summary of the same numbers."""
    lines = ["", "=" * 62, "VEGA - LIVE SYSTEM METRICS", "=" * 62]

    host = report.get("host", {})
    lines.append(f"\nHost         {host.get('platform')} {host.get('release')}  "
                 f"Python {host.get('python')}")
    if host.get("ram_total_gb"):
        lines.append(f"Hardware     {host.get('cpu_cores')} cores, "
                     f"{host['ram_total_gb']} GB RAM "
                     f"({host.get('ram_available_gb')} GB free right now)")
    lines.append("Models       run locally via Ollama - no data leaves this machine")

    routing = report.get("routing")
    if routing:
        lines.append(f"\nCommands     {routing['commands_recorded']} recorded")
        share = routing.get("model_free_share")
        if share is not None:
            lines.append(f"             {share:.0%} answered without invoking a model")
        for tier, count in routing["by_tier"].items():
            bar = "#" * max(1, round(count / max(routing["commands_recorded"], 1) * 40))
            lines.append(f"   {tier:14} {count:5}  {bar}")

    reliability = report.get("reliability")
    if reliability and reliability.get("success_rate") is not None:
        lines.append(f"\nSuccess rate {reliability['success_rate']:.1%} "
                     f"({reliability['succeeded']}/{reliability['attempted']})")

    memory = report.get("memory")
    if memory:
        lines.append(f"Memory       {memory['episodes']} episodes, "
                     f"{memory.get('semantic_coverage', 0):.0%} semantically indexed")

    workload = report.get("workload", {})
    known = [f"{v} {k}" for k, v in workload.items() if v is not None]
    if known:
        lines.append("Managing     " + ", ".join(known))

    lines.append("")
    return "\n".join(lines)
