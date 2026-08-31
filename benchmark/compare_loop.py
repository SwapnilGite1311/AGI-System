"""
Run the multi-step tasks two ways and compare.

This is the experiment the whole architecture argument rests on: does a
think-act-observe loop beat one-shot tier routing on goals that need a
second step informed by the first? Both paths get the same tasks, the same
tools, the same model, and the same verifiers.

    python benchmark/compare_loop.py
"""

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

from benchmark.multistep import MULTISTEP, MULTISTEP_VERSION  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
ANSI = re.compile(chr(27) + r"\[[0-9;]*m")


def _sandbox() -> tuple:
    box = Path(tempfile.mkdtemp(prefix="vega_cmp_"))
    config = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8-sig"))
    config.setdefault("paths", {})["data"] = str(box)
    if isinstance(config.get("session"), dict):
        for key in ("session_file", "preferences_file"):
            if config["session"].get(key):
                config["session"][key] = str(box / Path(config["session"][key]).name)
    (box / "business_tasks.json").write_text(json.dumps({"tasks": []}), encoding="utf-8")
    for name in ("team_members.json", "projects.json", "schedules.json"):
        (box / name).write_text("[]", encoding="utf-8")
    path = box / "settings.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path, box


async def _one_mode(mode: str) -> dict:
    """mode: 'tiers' (current routing) or 'react' (the loop)."""
    config_path, box = _sandbox()
    documents = box / "documents"
    documents.mkdir(exist_ok=True)

    import main as m
    from core.react_loop import ReactLoop

    controller = m.AutonomousSystemController(str(config_path))
    loop = ReactLoop(controller)
    ctx = {"data_dir": box, "documents_dir": documents, "project_root": ROOT}

    with contextlib.suppress(Exception):
        await controller.process_command("hello")

    rows = []
    print(f"\n--- {mode} " + "-" * (62 - len(mode)))
    for task in MULTISTEP:
        started = time.time()
        buffer = io.StringIO()
        result = {}
        try:
            if mode == "react":
                loop_result = await asyncio.wait_for(loop.run(task["command"]), timeout=240)
                result = loop_result.as_dict()
                # Everything the loop saw, so verifiers can read observations.
                output = "\n".join(
                    f"{s['action']}: {s['observation']}" for s in result["results"]
                ) + "\n" + result.get("answer", "")
            else:
                result = await asyncio.wait_for(
                    controller.process_command(task["command"]), timeout=240
                )
                with contextlib.redirect_stdout(buffer):
                    controller._display_result(result)
                output = ANSI.sub("", buffer.getvalue())
        except Exception as exc:
            output = f"EXCEPTION {type(exc).__name__}: {exc}"

        try:
            passed, detail = task["verify"](result, output, ctx)
        except Exception as exc:
            passed, detail = False, f"verifier raised {exc}"

        elapsed = round(time.time() - started, 1)
        rows.append({"id": task["id"], "command": task["command"],
                     "passed": bool(passed), "detail": detail,
                     "seconds": elapsed,
                     "steps": result.get("steps_total", 1)})
        print(f"  {'PASS' if passed else 'FAIL'}  {task['id']} {task['command'][:44]:46}"
              f" {elapsed:5.1f}s  {result.get('steps_total', 1)} steps"
              + ("" if passed else f"\n        -> {detail[:80]}"))

    with contextlib.suppress(Exception):
        await controller.shutdown()
    shutil.rmtree(box, ignore_errors=True)

    passed = sum(1 for r in rows if r["passed"])
    return {"mode": mode, "passed": passed, "total": len(rows),
            "rate": round(passed / len(rows), 3) if rows else 0.0,
            "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2] if rows else 0,
            "rows": rows}


async def _run() -> dict:
    print("=" * 70)
    print(f"MULTI-STEP COMPARISON  v{MULTISTEP_VERSION}   {len(MULTISTEP)} tasks")
    print("=" * 70)
    tiers = await _one_mode("tiers")
    react = await _one_mode("react")

    print("\n" + "=" * 70)
    print(f"  current tier routing   {tiers['rate']:5.1%}  "
          f"({tiers['passed']}/{tiers['total']})   median {tiers['median_seconds']}s")
    print(f"  react loop             {react['rate']:5.1%}  "
          f"({react['passed']}/{react['total']})   median {react['median_seconds']}s")
    delta = react["rate"] - tiers["rate"]
    print(f"  difference             {delta:+.1%}")
    print("=" * 70)

    print("\n  per task:")
    for a, b in zip(tiers["rows"], react["rows"]):
        mark = {(True, True): "both", (False, False): "neither",
                (True, False): "TIERS only", (False, True): "REACT only"}[(a["passed"], b["passed"])]
        print(f"    {a['id']}  {mark:11} {a['command'][:44]}")
    print()

    return {"run_at": datetime.now().isoformat(timespec="seconds"),
            "multistep_version": MULTISTEP_VERSION,
            "tiers": tiers, "react": react, "delta": round(delta, 3)}


def main() -> int:
    report = asyncio.run(_run())
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"{stamp}_multistep_comparison.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  saved to {out.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
