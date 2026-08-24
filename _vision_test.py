import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import asyncio


async def main():
    from main import AutonomousSystemController

    asc = AutonomousSystemController()
    for cmd in ["take a screenshot", "what is on my screen"]:
        print(f"\n=== {cmd!r} ===")
        t0 = time.perf_counter()
        r = await asyncio.wait_for(asc.process_command(cmd), timeout=240)
        print("time=%.1fs success=%s tier=%s" % (time.perf_counter() - t0, r.get("success"), r.get("tier")))
        for s in (r.get("results") or [])[:2]:
            if isinstance(s, dict):
                print("  desc:", str(s.get("description"))[:250])
                if s.get("error"):
                    print("  error:", str(s.get("error"))[:150])


asyncio.run(main())
