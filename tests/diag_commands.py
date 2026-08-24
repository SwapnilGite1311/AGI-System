"""Complex-command automation diagnostic - the hard paths."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import asyncio
import time


async def main():
    from main import AutonomousSystemController

    asc = AutonomousSystemController()
    print("\n=== COMPLEX COMMAND DIAGNOSTIC ===\n")

    commands = [
        "open google and search for amazon and search laptops on amazon",
        "send an email to thisaddress@gmail.com about the meeting",
        "fill out this form for me google.forms.com",
    ]

    for cmd in commands:
        print(f"\n{'='*64}\nCOMMAND: {cmd!r}")
        t0 = time.perf_counter()
        try:
            result = await asc.process_command(cmd)
        except Exception as exc:
            print(f"  CRASH after {time.perf_counter()-t0:.1f}s: {type(exc).__name__}: {str(exc)[:300]}")
            continue
        dt = time.perf_counter() - t0
        print(f"  total time: {dt:.1f}s")
        print(f"  success : {result.get('success')}")
        print(f"  tier    : {result.get('tier')}")
        if result.get("error"):
            print(f"  error   : {str(result.get('error'))[:250]}")
        plan = result.get("plan") or {}
        if isinstance(plan, dict):
            print(f"  strategy: {plan.get('strategy', 'n/a')} | steps in plan: {len(plan.get('steps', []) or [])}")
            for i, s in enumerate((plan.get("steps") or [])[:8]):
                if isinstance(s, dict):
                    print(f"    plan[{i}]: action={s.get('action') or s.get('intent', {}).get('type', '?')} desc={str(s.get('description') or s.get('command'))[:60]}")
        steps = result.get("results") or result.get("steps") or []
        for i, s in enumerate(steps[:10]):
            if isinstance(s, dict):
                desc = str(s.get("description") or s.get("action") or "?")[:70]
                ok = s.get("success")
                err = str(s.get("error"))[:150] if s.get("error") else ""
                print(f"    exec[{i}]: [{'OK' if ok else 'FAIL'}] {desc} {err}")
        resp = result.get("response")
        if resp:
            print(f"  response: {str(resp)[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
