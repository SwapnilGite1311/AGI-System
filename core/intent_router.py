"""
VEGA Brain - LLM intent understanding layer.

Instead of matching 70+ hardcoded phrase patterns, sends the user's sentence
plus the tool manifest to the local model ONCE and receives a strict JSON
decision: which registered tool-action to run, with parameters.

Design rules:
  - Only REGISTERED actions may be chosen; anything else is rejected upstream.
  - Low confidence or missing fields -> "clarify" action with a question,
    so VEGA asks the user instead of guessing.
  - Pure function of (command, manifest): no hidden state, fully testable.
"""

import json
import re
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

DECISION_SCHEMA_EXAMPLE = """{
  "action": "<one exact name from the list above>",
  "params": { ... },
  "confidence": 0.0-1.0
}"""

SYSTEM_RULES = """You are the intent understanding module of VEGA, an assistant that
executes real actions on this computer through TOOLS.

Choose exactly ONE tool action per user message and extract its parameters.
Rules:
- "action" MUST be one of the listed tool actions, spelled exactly.
- Put required values inside "params".
- If several independent steps are requested, still pick the single most
  important first action; the queue handles the rest.
- If the message is casual chat (greetings, feelings, questions about you),
  use action "chat" with params {"reply": "<short friendly answer>"}.
- If the request is unclear or you cannot confidently pick a tool, use
  action "clarify" with params {"question": "<one short question>"}.
- NEVER invent tools or parameters that are not listed.
Respond with ONLY valid JSON, no markdown, no explanations."""


class LLMIntentRouter:
    def __init__(self, config: Dict[str, Any], manifest_provider):
        ollama_cfg = config.get("ollama", {})
        self.host = ollama_cfg.get("host", "http://127.0.0.1:11434")
        self.timeout = int(ollama_cfg.get("timeout", 120))
        self.model = (config.get("intent_router") or {}).get(
            "model", (config.get("conversation") or {}).get("model", "qwen2.5:3b")
        )
        num_gpu = ollama_config_gpu(config)
        options = {"num_ctx": 2048, "temperature": 0.2}
        if num_gpu is not None:
            options["num_gpu"] = num_gpu
        self.options = options
        self.manifest_provider = manifest_provider
        # actions that are conversational, not tool executions
        self.soft_actions = {"chat", "clarify"}

    # ------------------------------------------------------------------
    def _build_prompt(self, command: str) -> str:
        manifest = self.manifest_provider() or []
        tool_lines = []
        for tool in manifest:
            actions = ", ".join(tool.get("actions", []))
            tool_lines.append(f"- {tool.get('name')}: {tool.get('description')} (actions: {actions})")
        return (
            SYSTEM_RULES
            + "\n\nAVAILABLE TOOLS:\n"
            + "\n".join(tool_lines)
            + "\n\nAdditional always-available soft actions: chat, clarify\n"
            + "\nResponse format example:\n"
            + DECISION_SCHEMA_EXAMPLE
            + "\n\nUSER MESSAGE:\n"
            + command
        )

    def _call_model(self, prompt: str) -> Optional[str]:
        try:
            resp = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": "5m",
                    "options": self.options,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as exc:
            logger.warning("IntentRouter model call failed: {}", str(exc)[:120])
            return None

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    def _known_actions(self) -> set:
        actions = set(self.soft_actions)
        for tool in self.manifest_provider() or []:
            actions.update(a.lower() for a in tool.get("actions", []))
        return actions

    # ------------------------------------------------------------------
    def decide(self, command: str) -> Optional[Dict[str, Any]]:
        """Return {'action','params','confidence'} or None on hard failure."""
        prompt = self._build_prompt(command)
        raw = self._call_model(prompt)
        decision = self._extract_json(raw)
        if not decision or "action" not in decision:
            logger.warning("IntentRouter produced no parsable decision.")
            return None

        action = str(decision.get("action", "")).strip().lower()
        params = decision.get("params") if isinstance(decision.get("params"), dict) else {}
        confidence = float(decision.get("confidence", 0.5) or 0.0)

        known = self._known_actions()
        if action not in known:
            logger.warning("IntentRouter chose unknown action '{}', clarifying.", action)
            return {
                "action": "clarify",
                "params": {
                    "question": f"I understood you want something ({action}), "
                                "but I don't have a tool for it. Can you rephrase?"
                },
                "confidence": confidence,
            }

        if confidence < 0.35 and action not in self.soft_actions:
            return {
                "action": "clarify",
                "params": {"question": f"Do you want me to {action}? Please confirm."},
                "confidence": confidence,
            }

        return {"action": action, "params": params, "confidence": confidence}


def ollama_config_gpu(config: Dict[str, Any]) -> Optional[int]:
    val = (config.get("ollama") or {}).get("num_gpu")
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None
