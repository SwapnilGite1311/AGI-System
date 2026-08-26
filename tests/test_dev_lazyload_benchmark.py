"""D-1: Measure lazy-load gains — boot time + idle RAM before/after.

Compares two scenarios against the live lazy-load architecture in main.py:
  eager  : constructs ALL agents up front (pre-lazy baseline simulation)
  lazy   : only conversation/learning/system pre-built (current behavior)

Method (no code changes to production files):
  - Import AutonomousSystemController once per scenario in a fresh subprocess.
  - Time __init__ wall-clock (boot time).
  - Read process RSS + system available RAM after init, then idle for
    IDLE_SECONDS and re-read RSS (idle RAM drift).
  - For the "eager" scenario we then touch every lazy key to force-construct
    all agents and measure the delta — this approximates the old eager boot.

Run:  python tests/test_dev_lazyload_benchmark.py
Output: printed table + JSON written to data/lazyload_report.json
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IDLE_SECONDS = 5

CHILD = r'''
import json, os, sys, time
sys.path.insert(0, os.getcwd())

scenario = sys.argv[1]
t0 = time.perf_counter()
from main import AutonomousSystemController
import psutil
proc = psutil.Process()
asc = AutonomousSystemController()
init_s = time.perf_counter() - t0

rss_before = proc.memory_info().rss / (1024 * 1024)
time.sleep(%d)
rss_after = proc.memory_info().rss / (1024 * 1024)

eager_touch_s = None
lazy_keys = ["conversation", "learning", "system", "vision", "file", "business",
             "web", "business_process", "security",
             "analytics", "advanced_neural", "meta_learning", "self_reflection",
             "autonomous_goals", "concept_discovery", "self_programming",
             "algorithm_optimization", "self_evolving", "cognitive"]
built = sorted(k for k in lazy_keys if k in getattr(asc.agents, "_cache", {}))
if scenario == "eager":
    t1 = time.perf_counter()
    for k in lazy_keys:
        try:
            _ = asc.agents[k]
        except Exception:
            pass
    eager_touch_s = time.perf_counter() - t1

out = {
    "scenario": scenario,
    "boot_init_seconds": round(init_s, 2),
    "agents_prebuilt": built,
    "rss_idle_start_mb": round(rss_before, 1),
    "rss_idle_end_mb": round(rss_after, 1),
    "all_agents_touch_seconds": round(eager_touch_s, 2) if eager_touch_s is not None else None,
    "vm_avail_mb": round(psutil.virtual_memory().available / (1024 * 1024), 1),
}
print("@@RESULT@@" + json.dumps(out))
''' % IDLE_SECONDS


def run_scenario(scenario: str) -> dict:
    # fresh interpreter each run so agent caches don't leak between scenarios
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, scenario],
        cwd=str(PROJECT_ROOT),
        capture_output=True, text=True, timeout=600,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    for line in proc.stdout.splitlines():
        if line.startswith("@@RESULT@@"):
            return json.loads(line[len("@@RESULT@@"):])
    print(proc.stdout[-2000:])
    print(proc.stderr[-3000:], file=sys.stderr)
    raise RuntimeError(f"scenario {scenario} produced no result")


def main():
    results = [run_scenario("lazy"), run_scenario("eager")]
    lazy, eager = results

    print("\n===== D-1 LAZY-LOAD GAINS REPORT =====")
    print(f"idle window measured: {IDLE_SECONDS}s")
    print(f"{'metric':<32}{'lazy (current)':>18}{'eager (old-style)':>20}")
    print(f"{'boot __init__ time (s)':<32}{lazy['boot_init_seconds']:>18}{eager['boot_init_seconds'] + (eager['all_agents_touch_seconds'] or 0):>20}")
    print(f"{'RSS idle end (MB)':<32}{lazy['rss_idle_end_mb']:>18}{eager['rss_idle_end_mb']:>20}")
    print(f"{'system avail RAM (MB)':<32}{lazy['vm_avail_mb']:>18}{eager['vm_avail_mb']:>20}")
    print(f"prebuilt agents (lazy): {', '.join(lazy['agents_prebuilt'])}")

    out = PROJECT_ROOT / "data" / "lazyload_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nsaved: {out}")


if __name__ == "__main__":
    main()
