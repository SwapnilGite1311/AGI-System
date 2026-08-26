import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncio


async def main():
    from main import AutonomousSystemController

    asc = AutonomousSystemController()

    tests = [
        ("search for gaming laptops on amazon.in and create a task to compare their prices", "multi-action PLAN"),
        ("take a screenshot and then list files in documents", "multi-action PLAN"),
        ("hello there, how are you feeling today?", "chat"),
    ]
    for cmd, kind in tests:
        print(f"\n=== [{kind}] {cmd!r} ===")
        t0 = time.perf_counter()
        try:
            r = await asyncio.wait_for(asc.process_command(cmd), timeout=240)
            dt = time.perf_counter() - t0
            steps = [s for s in (r.get("results") or []) if isinstance(s, dict)]
            print(f"{dt:.1f}s tier={r.get('tier')} success={r.get('success')} steps={len(steps)}")
            for i, s in enumerate(steps[:5]):
                desc = str(s.get("subtask_description") or s.get("message") or s.get("action") or "?")[:60]
                err = str(s.get("error"))[:80] if s.get("error") else ""
                print(f"  step{i+1}: [{'OK' if s.get('success') else 'FAIL'}] {desc} {err}")
            if r.get("error"):
                print("  error:", str(r.get("error"))[:150])
        except Exception as exc:
            print(f"EXC {time.perf_counter()-t0:.1f}s {type(exc).__name__}: {str(exc)[:120]}")

    # Follow-up context test
    print("\n=== [FOLLOW-UP] now email that summary to swapnilgite9028@gmail.com ===")
    t0 = time.perf_counter()
    r = await asyncio.wait_for(
        asc.process_command("email that summary to swapnilgite9028@gmail.com"), timeout=240
    )
    print(f"{time.perf_counter()-t0:.1f}s tier={r.get('tier')} success={r.get('success')}")
    resp = str(r.get("response") or "")[:120]
    print("reply:", resp)


asyncio.run(main())
