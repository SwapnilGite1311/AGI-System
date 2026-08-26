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
        "create a file named vega_brain.txt with content hello world and tell few things about yourself",
        "which disk drives are present on this device?",
        "suggest me laptops under 100000",
        "hey there how are you today?",
    ]
    for cmd in tests:
        print(f"\n=== {cmd!r} ===")
        t0 = time.perf_counter()
        try:
            r = await asyncio.wait_for(asc.process_command(cmd), timeout=150)
            dt = time.perf_counter() - t0
            print(f"{dt:.1f}s tier={r.get('tier')} success={r.get('success')}")
            resp = r.get("response")
            if resp:
                print("reply:", str(resp)[:180])
            for s in (r.get("results") or [])[:3]:
                if isinstance(s, dict):
                    print("  step:", s.get("action"), "| ok:", s.get("success"),
                          "| desc:", str(s.get("subtask_description"))[:50],
                          ("| err: " + str(s.get("error"))[:80]) if s.get("error") else "")
        except Exception as exc:
            print(f"FAIL {time.perf_counter()-t0:.1f}s {type(exc).__name__}: {str(exc)[:120]}")


asyncio.run(main())
