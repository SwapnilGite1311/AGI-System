"""Live smoke test for the two-tier model rework (fix #1)."""
import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\Swapnil gite\LAN\PROJECTS\Agentic Web\AGI-System")

from core.council import LLMCouncil
from core.chairman import Chairman
from agents.conversation_agent import ConversationAgent


async def main():
    council = LLMCouncil()
    chairman = Chairman()
    conv = ConversationAgent()

    print("=== 1. Simple decision (speed tier) ===")
    r = await council.decide("open chrome", "simple")
    print(json.dumps(r, indent=2, default=str)[:600])

    print("\n=== 2. Medium decision (strategist) ===")
    r = await council.decide("send an email to test@example.com about tomorrow's meeting", "medium")
    print(json.dumps(r, indent=2, default=str)[:600])

    print("\n=== 3. Complex decision (sequential council + chairman) ===")
    r = await council.decide("organize my downloads folder by file type", "complex")
    print(json.dumps(r, indent=2, default=str)[:600])

    print("\n=== 4. Chairman plan validation ===")
    v = await chairman.validate_plan(
        {"steps": [{"action": "create_file", "params": {"path": "notes.txt", "content": "hi"}}]},
        "create a notes file",
    )
    print(json.dumps(v, indent=2, default=str)[:400])

    print("\n=== 5. Conversation chat ===")
    c = await conv.chat("what are you capable of?")
    print(c.get("model"), "->", c.get("response", "")[:200])

    print("\nALL SMOKE TESTS COMPLETED")


if __name__ == "__main__":
    asyncio.run(main())
