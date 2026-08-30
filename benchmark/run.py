"""
Run the frozen benchmark and record the score.

    python benchmark/run.py                 # run it, print a report
    python benchmark/run.py --label before  # tag the run for comparison
    python benchmark/run.py --compare       # show every recorded run

Results land in benchmark/results/ as JSON so two runs can be compared
directly - which is the entire point. A single score tells you nothing; the
difference between two tells you whether a change helped.

Runs against an ISOLATED data directory. The test suite used to write into
the live store, which is how 1,400 junk tasks and a recurring "Test
Reminder" got there; a benchmark that ran repeatedly would be far worse.
"""

import argparse
import asyncio
import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark.tasks import BENCHMARK_VERSION, CATEGORIES, TASKS  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
ANSI = re.compile(chr(27) + r"\[[0-9;]*m")


def _isolated_config() -> tuple:
    """A copy of the real config pointing at a throwaway data directory."""
    sandbox = Path(tempfile.mkdtemp(prefix="vega_bench_"))
    real_config = ROOT / "config" / "settings.json"
    config = json.loads(real_config.read_text(encoding="utf-8-sig"))

    config.setdefault("paths", {})["data"] = str(sandbox)
    for key in ("session_file", "preferences_file"):
        if isinstance(config.get("session"), dict) and config["session"].get(key):
            config["session"][key] = str(sandbox / Path(config["session"][key]).name)

    # Seed the shapes the tasks expect to read back.
    (sandbox / "business_tasks.json").write_text(
        json.dumps({"tasks": [], "updated_at": datetime.now().isoformat()}), encoding="utf-8")
    for name in ("team_members.json", "projects.json", "schedules.json"):
        (sandbox / name).write_text("[]", encoding="utf-8")

    path = sandbox / "settings.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path, sandbox


async def _run(label: str) -> dict:
    config_path, sandbox = _isolated_config()
    documents = sandbox / "documents"
    documents.mkdir(exist_ok=True)

    import main as m

    controller = m.AutonomousSystemController(str(config_path))
    ctx = {
        "data_dir": sandbox,
        "documents_dir": documents,
        "project_root": ROOT,
    }

    # Warm the model so the first task is not timed against a cold load.
    with contextlib.suppress(Exception):
        await controller.process_command("hello")

    rows = []
    print(f"\nrunning {len(TASKS)} tasks\n" + "-" * 70)

    for task in TASKS:
        if task.setup:
            with contextlib.suppress(Exception):
                task.setup(ctx)

        started = time.time()
        buffer = io.StringIO()
        result, error = {}, None
        try:
            result = await asyncio.wait_for(
                controller.process_command(task.command), timeout=180
            )
            with contextlib.redirect_stdout(buffer):
                controller._display_result(result)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        elapsed = round(time.time() - started, 1)
        output = ANSI.sub("", buffer.getvalue())

        if error:
            passed, detail = False, f"raised {error}"
        else:
            try:
                passed, detail = task.verify(result, output, ctx)
            except Exception as exc:
                passed, detail = False, f"verifier raised {type(exc).__name__}: {exc}"

        rows.append({
            "id": task.id, "category": task.category, "command": task.command,
            "intent": task.intent, "weight": task.weight,
            "passed": bool(passed), "detail": detail,
            "seconds": elapsed, "tier": result.get("tier"),
        })
        mark = "PASS" if passed else "FAIL"
        print(f"  {mark}  {task.id:3} {task.command[:42]:44} {elapsed:5.1f}s"
              + ("" if passed else f"\n         -> {detail[:90]}"))

    with contextlib.suppress(Exception):
        await controller.shutdown()
    shutil.rmtree(sandbox, ignore_errors=True)

    earned = sum(r["weight"] for r in rows if r["passed"])
    total = sum(r["weight"] for r in rows)
    by_category = {}
    for category in CATEGORIES:
        subset = [r for r in rows if r["category"] == category]
        got = sum(r["weight"] for r in subset if r["passed"])
        out_of = sum(r["weight"] for r in subset)
        by_category[category] = {"earned": got, "total": out_of,
                                 "rate": round(got / out_of, 3) if out_of else 0.0}

    return {
        "label": label,
        "benchmark_version": BENCHMARK_VERSION,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "score": round(earned / total, 3) if total else 0.0,
        "earned": earned, "total": total,
        "passed": sum(1 for r in rows if r["passed"]), "tasks": len(rows),
        "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2] if rows else 0,
        "by_category": by_category,
        "rows": rows,
    }


def _report(run: dict) -> None:
    print("\n" + "=" * 70)
    print(f"BENCHMARK v{run['benchmark_version']}   label: {run['label']}")
    print("=" * 70)
    print(f"  score          {run['score']:.1%}   ({run['earned']}/{run['total']} weighted)")
    print(f"  tasks passed   {run['passed']}/{run['tasks']}")
    print(f"  median time    {run['median_seconds']}s")
    print("\n  by category:")
    for category, stats in sorted(run["by_category"].items(),
                                  key=lambda kv: kv[1]["rate"]):
        bar = "#" * round(stats["rate"] * 30)
        print(f"    {category:14} {stats['rate']:5.0%}  {bar}")

    failed = [r for r in run["rows"] if not r["passed"]]
    if failed:
        print(f"\n  failures ({len(failed)}):")
        for r in failed:
            print(f"    {r['id']:3} {r['command'][:40]:42} {r['detail'][:60]}")
    print()


def _compare() -> int:
    runs = sorted(RESULTS_DIR.glob("*.json"))
    if not runs:
        print("no recorded runs yet")
        return 0
    print(f"\n{'label':22} {'when':18} {'score':>7}  by category")
    print("-" * 78)
    for path in runs:
        run = json.loads(path.read_text(encoding="utf-8"))
        worst = sorted(run["by_category"].items(), key=lambda kv: kv[1]["rate"])[:3]
        summary = "  ".join(f"{c}:{s['rate']:.0%}" for c, s in worst)
        print(f"{run['label'][:22]:22} {run['run_at'][:16]:18} {run['score']:6.1%}  {summary}")
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="run")
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()

    if args.compare:
        return _compare()

    run = asyncio.run(_run(args.label))
    _report(run)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"{stamp}_{re.sub(r'[^a-zA-Z0-9_-]', '_', args.label)}.json"
    out.write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(f"  saved to {out.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
