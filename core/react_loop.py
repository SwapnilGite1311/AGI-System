"""
A think-act-observe agent loop.

The existing tiers classify a command once and execute once. Nothing the
tool returns ever reaches the model, so a plan built on a wrong assumption
runs to completion anyway - "research X and write me a report" searched the
web, ignored what came back, and wrote a file from nothing. That is why the
system reads as a command router: structurally it is one.

This loop closes that gap:

    think -> act -> observe -> think -> ... -> finish

Each step the model sees what actually happened and decides the next move,
until it declares the goal met or hits a cap.

It is deliberately NOT a replacement for the fast path. 62% of real
commands are answered deterministically in ~0.2s with no model at all;
routing those through a loop would make them slower and less reliable for
no gain. This exists for the multi-step work the single-shot tiers cannot
do, and the benchmark decides where the boundary sits.

Safety is unchanged: every action goes through the same ToolRegistry the
other tiers use, so the same guards apply. The loop adds three of its own -
a step cap, a repetition check, and a rule that an action which failed the
same way twice is not retried a third time.
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

MAX_STEPS = 6
MAX_OBSERVATION_CHARS = 700
REPEAT_LIMIT = 2


@dataclass
class Step:
    number: int
    thought: str
    action: str
    params: Dict[str, Any]
    observation: str
    success: bool
    seconds: float


@dataclass
class LoopResult:
    goal: str
    steps: List[Step] = field(default_factory=list)
    finished: bool = False
    answer: str = ""
    stop_reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "success": self.finished,
            "tier": "react",
            "goal": self.goal,
            "answer": self.answer,
            "stop_reason": self.stop_reason,
            "steps_total": len(self.steps),
            "steps_completed": sum(1 for s in self.steps if s.success),
            "results": [
                {
                    "step": s.number,
                    "thought": s.thought,
                    "action": s.action,
                    "params": s.params,
                    "observation": s.observation,
                    "success": s.success,
                    "seconds": s.seconds,
                }
                for s in self.steps
            ],
        }


def _summarise(value: Any) -> str:
    """Compress a tool result into something a small model can read.

    Feeding raw JSON back wastes most of a 4k context on ids and timestamps,
    and a 3B model then loses the thread entirely.
    """
    if value is None:
        return "no result"
    if isinstance(value, str):
        return value[:MAX_OBSERVATION_CHARS]

    if isinstance(value, dict):
        if value.get("error"):
            return f"FAILED: {str(value['error'])[:300]}"

        parts = []
        for key in ("message", "path", "text", "screen_text", "answer", "result",
                    "output", "url", "count", "total"):
            if value.get(key) not in (None, "", [], {}):
                parts.append(f"{key}={str(value[key])[:200]}")

        for key, item in value.items():
            if isinstance(item, list) and item:
                sample = ", ".join(
                    str(x.get("name") or x.get("title") or x.get("device") or x)[:40]
                    if isinstance(x, dict) else str(x)[:40]
                    for x in item[:5]
                )
                parts.append(f"{key}: {len(item)} items [{sample}]")

        if not parts:
            # An action can "succeed" and produce nothing useful - a shell
            # command with empty stdout, for instance. Dumping the raw JSON
            # let the model read {"success": true, "output": ""} as progress
            # and repeat the same step six times. Say it plainly instead.
            if value.get("success") is True:
                return ("the action reported success but returned no data - "
                        "it did not produce anything usable")
            parts.append(json.dumps(value, default=str)[:MAX_OBSERVATION_CHARS])
        return "; ".join(parts)[:MAX_OBSERVATION_CHARS]

    return str(value)[:MAX_OBSERVATION_CHARS]


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first JSON object out of a model reply."""
    if not text:
        return None
    cleaned = text.strip().replace("```json", "").replace("```", "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    for candidate in (cleaned[start:end + 1], cleaned[start:cleaned.find("}", start) + 1]):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


class ReactLoop:
    """Runs one goal to completion, or to a stopping condition."""

    def __init__(self, controller, max_steps: int = MAX_STEPS):
        self.controller = controller
        self.max_steps = max_steps

    # -- prompt ----------------------------------------------------------

    # Actions the loop is not offered. run_command is a raw shell escape
    # hatch: the model reached for it for every goal, got empty stdout back,
    # and never used the structured tools that would have worked. Excluding
    # it costs nothing here, because anything it could do is available as a
    # real tool with a real result.
    EXCLUDED_ACTIONS = frozenset({
        "run_command", "run_powershell", "shell", "execute_command",
    })

    def _tool_lines(self) -> str:
        lines = []
        for tool in self.controller.get_tool_manifest():
            usable = [a for a in tool.get("actions", [])
                      if a not in self.EXCLUDED_ACTIONS]
            if not usable:
                continue
            actions = ", ".join(usable[:6])
            lines.append(f"- {tool['name']}: {tool.get('description','')[:130]}\n"
                         f"    actions: {actions}")
        return "\n".join(lines)

    def _resolve_action(self, action: str, goal: str) -> str:
        """Map a tool name onto one of its actions, if that is what was given."""
        registry = getattr(self.controller, "tool_registry", None)
        if registry and registry.resolve(action):
            return action                       # already a valid action

        for tool in self.controller.get_tool_manifest():
            if str(tool.get("name", "")).lower() != action.lower():
                continue
            usable = [a for a in tool.get("actions", [])
                      if a not in self.EXCLUDED_ACTIONS]
            if not usable:
                return action
            # Prefer an action whose name appears in the goal, so
            # "how much disk space" picks disk_drives over status.
            lowered = goal.lower()
            for candidate in usable:
                if candidate.replace("_", " ") in lowered:
                    return candidate
            for candidate in usable:
                if any(part in lowered for part in candidate.split("_") if len(part) > 3):
                    return candidate
            return usable[0]
        return action

    def _build_prompt(self, goal: str, steps: List[Step]) -> str:
        history = ""
        for step in steps:
            history += (
                f"\nStep {step.number}:\n"
                f"  thought: {step.thought}\n"
                f"  action: {step.action} {json.dumps(step.params)}\n"
                f"  observation: {step.observation}\n"
            )
        if not history:
            history = "\n(nothing done yet)\n"

        return f"""You are working towards a goal, one step at a time.

GOAL: {goal}

TOOLS:
{self._tool_lines()}

WHAT HAS HAPPENED SO FAR:{history}

Decide the SINGLE next step. Look at the observations above - if a step
already produced what the goal needs, finish instead of repeating it.

Reply with ONLY JSON, one of:

  {{"thought": "why this step", "action": "<action name>", "params": {{...}}}}

  {{"thought": "why we are done", "finish": true, "answer": "what was achieved"}}

Rules:
- action must be one of the action names listed above, exactly.
- Do not repeat an action that already succeeded.
- If an action failed twice, try a different approach or finish.
- Prefer finishing over padding with extra steps."""

    # -- loop ------------------------------------------------------------

    async def run(self, goal: str) -> LoopResult:
        result = LoopResult(goal=goal)
        attempts: Dict[str, int] = {}
        failures: Dict[str, int] = {}

        for number in range(1, self.max_steps + 1):
            decision = await self._think(goal, result.steps)
            if decision is None:
                result.stop_reason = "the model did not return a usable step"
                break

            if decision.get("finish"):
                result.finished = True
                result.answer = str(decision.get("answer") or "").strip()
                result.stop_reason = "model reported the goal met"
                break

            action = str(decision.get("action") or "").strip()
            params = decision.get("params") or {}
            if not isinstance(params, dict):
                params = {}
            if not action:
                result.stop_reason = "model proposed a step with no action"
                break
            if action in self.EXCLUDED_ACTIONS:
                result.stop_reason = f"'{action}' is not available to this loop"
                break

            # Models routinely answer with the TOOL name ("system_ops")
            # where an action name belongs, then burn every remaining step
            # retrying it. Resolve it rather than failing on a naming
            # convention the user never sees.
            action = self._resolve_action(action, goal)

            # Repetition guard. The first version only counted FAILURES, so
            # a step that "succeeded" while achieving nothing could repeat
            # until the step cap - which is exactly what happened.
            signature = f"{action}:{json.dumps(params, sort_keys=True, default=str)[:120]}"
            attempts[signature] = attempts.get(signature, 0) + 1
            if attempts[signature] > REPEAT_LIMIT:
                result.stop_reason = (
                    f"'{action}' was attempted {REPEAT_LIMIT + 1} times with the same "
                    "arguments and is not making progress"
                )
                break

            started = time.time()
            try:
                observation_raw = await self.controller.tool_registry.execute(
                    action, params, goal
                )
                ok = bool(observation_raw.get("success", True)) and not observation_raw.get("error")
            except Exception as exc:
                observation_raw = {"error": f"{type(exc).__name__}: {exc}"}
                ok = False

            if not ok:
                failures[signature] = failures.get(signature, 0) + 1

            observation = _summarise(observation_raw)
            # A 628-row list summarised to its first five entries told the
            # model nothing about whether the thing it just created is in
            # there, so it listed again and again. Answer that directly.
            observation += self._presence_note(goal, observation_raw)

            result.steps.append(Step(
                number=number,
                thought=str(decision.get("thought") or "")[:200],
                action=action,
                params=params,
                observation=observation,
                success=ok,
                seconds=round(time.time() - started, 2),
            ))
            logger.info("[ReAct] step {}: {} -> {}", number, action,
                        "ok" if ok else "failed")

        if not result.finished and not result.stop_reason:
            result.stop_reason = f"reached the {self.max_steps}-step limit"

        # Even an unfinished run may have achieved something; say what.
        if not result.answer:
            done = [s for s in result.steps if s.success]
            result.answer = (
                "; ".join(f"{s.action}" for s in done) if done else "nothing completed"
            )
        return result

    # Words that end a name in an instruction: "a task called react probe
    # THEN list the tasks" - without these the capture ran to the length
    # cap and produced the needle "react probe then list the tasks to confi".
    _NAME_STOP = (
        "then", "and", "to confirm", "to check", "after", "so that",
        "which", "that is", "with", "containing", "afterwards", "next",
    )

    @classmethod
    def _presence_note(cls, goal: str, raw) -> str:
        """Say whether a distinctive phrase from the goal is in the result.

        A 629-row list summarised to its first five entries told the model
        nothing about whether the item it had just created was present, so
        it listed again and again until the repeat guard stopped it.
        """
        if not isinstance(raw, dict):
            return ""
        import re as _re

        candidates = _re.findall(r"[\"']([^\"']{3,40})[\"']", goal)
        candidates += _re.findall(
            r"\b(?:called|named|titled)\s+(.{3,60})", goal, _re.I
        )

        needles = []
        for candidate in candidates:
            text = candidate.strip()
            lowered = text.lower()
            for stop in cls._NAME_STOP:
                index = lowered.find(f" {stop}")
                if index > 0:
                    text = text[:index]
                    lowered = text.lower()
            text = text.strip(" .,;:'\"")
            if 2 < len(text) <= 40:
                needles.append(text.lower())

        if not needles:
            return ""

        blob = json.dumps(raw, default=str).lower()
        for needle in needles:
            if needle in blob:
                return f" | CONFIRMED: '{needle}' is present in this result"
        return f" | NOT FOUND: '{needles[0]}' is not in this result"

    async def _think(self, goal: str, steps: List[Step]) -> Optional[Dict[str, Any]]:
        prompt = self._build_prompt(goal, steps)
        try:
            response = await self.controller.council.ollama.generate(
                model=self.controller.council._select_model_for_member("strategist"),
                prompt=prompt,
                keep_alive=self.controller.council.keep_alive,
                options={"temperature": 0.1, "num_predict": 220},
            )
            return _extract_json(response.get("response", ""))
        except Exception as exc:
            logger.warning("[ReAct] thinking step failed: {}", str(exc)[:120])
            return None
