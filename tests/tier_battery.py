import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncio


async def main():
    from main import AutonomousSystemController

    asc = AutonomousSystemController()
    battery = [
        ("show system info", "direct"),
        ("hello", "conversation"),
        ("suggest me laptops under 100000", "single_model"),
        ("navigate to amazon.in and search for laptops", "sequential"),
    ]
    results = []
    for cmd, expected_tier in battery:
        print(f"\n--- {cmd!r} (expect {expected_tier}) ---")
        t0 = time.perf_counter()
        try:
            r = await asyncio.wait_for(asc.process_command(cmd), timeout=180)
            tier = r.get("tier")
            dt = time.perf_counter() - t0
            ok = tier == expected_tier
            results.append(ok)
            print(f"{'PASS' if ok else 'TIER-MISMATCH'} {dt:.1f}s tier={tier} success={r.get('success')}")
        except Exception as exc:
            results.append(False)
            print(f"FAIL {time.perf_counter()-t0:.1f}s {type(exc).__name__}: {str(exc)[:100]}")

    passed = sum(results)
    print(f"\nTIER BATTERY: {passed}/{len(results)} correct")
    sys.exit(0 if passed == len(results) else 1)


asyncio.run(main())
