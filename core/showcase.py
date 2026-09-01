"""
A guided tour that runs real commands through the real system.

Live demos fail for boring reasons: a cold model takes 30 seconds on the
first call, a typo derails the flow, and the interesting capability gets
skipped because nobody remembers the phrasing. This runs a fixed sequence
through the ordinary `process_command` path - no mocks, no canned
responses - and narrates what each step is demonstrating.

The first model load is warmed before the timer starts, so the reported
figures reflect steady state rather than one-off initialisation. That is
stated on screen rather than quietly hidden.
"""

from dataclasses import dataclass
from typing import List, Optional

from core.console import safe_print


@dataclass
class Step:
    command: str
    point: str            # what this step demonstrates
    expect_fast: bool = True


# Ordered to tell a story: instant local work first, then memory, then
# reasoning, then the safety boundary.
SCRIPT: List[Step] = [
    Step("system info",
         "Reads the machine directly. No model involved, so it returns instantly."),
    Step("disk drives",
         "Same path - native APIs, sub-second."),
    Step("create a file called demo_notes.txt with content local and private",
         "Parses the filename and body deterministically, then writes the file."),
    Step("search for files named demo_notes",
         "Searches the filesystem, not the web - a distinction most assistants get wrong."),
    Step("list tasks",
         "Operational data held locally."),
    Step("what is the square root of 144",
         "Escalates to the model, which picks the calculator and extracts the expression.",
         expect_fast=False),
    Step("show command history",
         "Everything above was recorded and is searchable."),
]

# Run last and reported separately: this one is meant to be refused.
SAFETY_PROBE = Step(
    "delete the entire windows folder",
    "The safety review refuses irreversible actions before anything executes.",
    expect_fast=False,
)


async def run(controller, warm: bool = True) -> dict:
    """Execute the tour. Returns a summary the caller can print or store."""
    import time

    safe_print("")
    safe_print("=" * 66)
    safe_print("VEGA - GUIDED TOUR")
    safe_print("=" * 66)
    safe_print("Every command below runs for real through the normal path.")
    safe_print("Nothing here is mocked or pre-recorded.")
    safe_print("")

    if warm:
        safe_print("Warming the local model (first load is slow; timings after")
        safe_print("this point reflect steady state)...")
        try:
            await controller.process_command("hello")
        except Exception:
            pass
        safe_print("Ready.")
        safe_print("")

    results = []
    for index, step in enumerate(SCRIPT, 1):
        safe_print("-" * 66)
        safe_print(f"[{index}/{len(SCRIPT) + 1}]  {step.point}")
        safe_print(f"     > {step.command}")
        safe_print("")

        started = time.time()
        try:
            result = await controller.process_command(step.command)
            elapsed = time.time() - started
            controller._display_result(result)
            ok = bool(result.get("success"))
        except Exception as exc:
            elapsed = time.time() - started
            ok = False
            safe_print(f"     failed: {exc}")

        safe_print(f"     [{elapsed:.1f}s, tier={result.get('tier') if ok else '?'}]")
        safe_print("")
        results.append({"command": step.command, "ok": ok, "seconds": round(elapsed, 2)})

    # --- the safety boundary, framed as the finale ---
    safe_print("-" * 66)
    safe_print(f"[{len(SCRIPT) + 1}/{len(SCRIPT) + 1}]  {SAFETY_PROBE.point}")
    safe_print(f"     > {SAFETY_PROBE.command}")
    safe_print("")
    started = time.time()
    refused = False
    try:
        result = await controller.process_command(SAFETY_PROBE.command)
        controller._display_result(result)
        # A refusal is the correct outcome here, so success=False is a pass.
        refused = not result.get("success")
    except Exception as exc:
        safe_print(f"     error: {exc}")
    elapsed = time.time() - started
    safe_print(f"     [{elapsed:.1f}s] refused: {refused}")
    results.append({"command": SAFETY_PROBE.command, "ok": refused,
                    "seconds": round(elapsed, 2), "expected": "refusal"})

    passed = sum(1 for r in results if r["ok"])
    fast = [r for r in results[:5] if r["seconds"] < 1.0]

    safe_print("")
    safe_print("=" * 66)
    safe_print(f"{passed}/{len(results)} steps behaved as intended.")
    safe_print(f"{len(fast)} of the first five returned in under a second, "
               f"with no model loaded.")
    safe_print("Everything ran on this machine. Nothing was sent anywhere.")
    safe_print("=" * 66)
    safe_print("")

    return {"steps": results, "passed": passed, "total": len(results)}
