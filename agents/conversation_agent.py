"""
Conversation Agent - natural chat layer for ASC.

This keeps ordinary conversation separate from tool execution, while still
allowing local models to answer when Ollama is available.
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger
from ollama import AsyncClient


class ConversationAgent:
    """Handles non-task chat and capability explanations."""

    def __init__(self, config_path: str = "./config/settings.json"):
        with open(config_path, "r", encoding="utf-8") as file:
            self.config = json.load(file)

        self.ollama = AsyncClient(host=self.config["ollama"]["host"])
        ollama_config = self.config.get("ollama", {})
        self.ollama_timeout = float(ollama_config.get("timeout", 120))
        self.keep_alive = str(ollama_config.get("keep_alive", "5m"))
        num_gpu = ollama_config.get("num_gpu")
        self.base_options = {"num_ctx": 2048}
        if num_gpu is not None:
            self.base_options["num_gpu"] = int(num_gpu)
        conversation_config = self.config.get("conversation", {})
        council_config = self.config.get("llm_council", {})
        self.model = conversation_config.get(
            "model",
            council_config.get("speed", {}).get("model", "gemma2:2b"),
        )
        self.history_limit = int(conversation_config.get("history_limit", 8))
        self.use_llm = bool(conversation_config.get("use_local_llm", True))
        self.history: List[Dict[str, str]] = []

        logger.info("Conversation Agent initialized")

    def is_conversation(self, text: str) -> bool:
        """Return True when text is chat/question rather than an action request."""

        normalized = " ".join((text or "").lower().strip().split())
        if not normalized:
            return False

        # Capability questions are ALWAYS conversation, even when phrased with
        # action verbs ("list out the things that you can do").
        capability_patterns = [
            r"\bwhat (can|could) you do\b",
            r"\bwhat you can do\b",
            r"\bthings that you can do\b",
            r"\bwhat (are|is) your (capabilities|abilities|features|skills)\b",
            r"\btell me .*capab",
            r"\byour capabilities\b",
        ]
        if any(re.search(p, normalized) for p in capability_patterns):
            return True

        # User feedback/complaints about ASC's own behaviour must never be
        # executed as commands ("you didn't opened chrome at all!").
        feedback_patterns = [
            r"^you (didn'?t|did not|don'?t|do not|never)\b",
            r"\byou (didn'?t|did not) (open|launch|start|do|create|send|search)\b",
            r"^(that|this|it) ('s |is |was )?(wrong|broken|failed|not working)",
            r"^(it|that) didn'?t work",
            r"^wrong\b",
            r"^try again",
        ]
        if any(re.search(p, normalized) for p in feedback_patterns):
            return True

        action_prefixes = (
            "open ", "launch ", "start ", "search ", "google ", "look up ",
            "find ", "go to ", "goto ", "navigate ", "fill ", "create ",
            "make ", "list files", "list tasks", "show system", "show cpu", "show ram",
            "run ", "copy ", "move ", "delete ", "organize ", "backup ",
            "compare ", "download ", "scan ", "check ssl", "dns lookup",
            "analyze disk", "voice ", "check voice",
        )
        if normalized.startswith(action_prefixes):
            return False

        conversation_patterns = [
            r"^(hi|hello|hey|yo|namaste|good morning|good afternoon|good evening)\b",
            r"\bhow are you\b",
            r"\bwhat can you do\b",
            r"\bwho are you\b",
            r"\bwhat are you capable of\b",
            r"\bwhat you are capable of\b",
            r"\btell me .*capable\b",
            r"\btell me .*can do\b",
            r"\btell me about yourself\b",
            r"\bcan we talk\b",
            r"\bthanks?\b",
        ]
        if any(re.search(pattern, normalized) for pattern in conversation_patterns):
            return True

        if normalized.endswith("?") and not any(word in normalized for word in ["file", "folder", "process", "chrome", "website", "form"]):
            return True

        return False

    async def chat(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Answer conversationally using local LLM when possible, fallback otherwise."""

        fallback = self._fallback_response(message, context)
        if not self.use_llm:
            return fallback

        try:
            prompt = self._build_prompt(message, context)
            response = await asyncio.wait_for(
                self.ollama.generate(
                    model=self.model,
                    prompt=prompt,
                    keep_alive=self.keep_alive,
                    options=dict(self.base_options),
                ),
                timeout=self.ollama_timeout,
            )
            text = response.get("response", "").strip()
            if not text:
                return fallback

            self._remember(message, text)
            return {
                "success": True,
                "tier": "conversation",
                "mode": "chat",
                "response": text,
                "model": self.model,
            }
        except Exception as exc:
            logger.warning("Conversation LLM unavailable, using fallback: {}", str(exc))
            fallback["llm_error"] = str(exc)
            return fallback

    def _build_prompt(self, message: str, context: Optional[Dict[str, Any]]) -> str:
        recent = "\n".join(
            f"User: {item['user']}\nASC: {item['assistant']}"
            for item in self.history[-self.history_limit:]
        )
        capability_summary = self._capability_summary(context)
        return f"""You are ASC, a sophisticated local AI assistant inspired by Jarvis. You are warm, intelligent, and helpful.

You should:
- Be conversational and natural
- Show understanding of context
- Be helpful and proactive
- Maintain a professional yet friendly tone
- When asked about actions, explain what you can do
- Show personality without being robotic

Capabilities:
{capability_summary}

Recent conversation:
{recent or "No prior conversation."}

User: {message}

Reply conversationally as Jarvis would - intelligent, helpful, and with personality. If the user asks for an action, tell them you can perform it as a command.
ASC:"""

    def _fallback_response(self, message: str, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = " ".join((message or "").lower().strip().split())

        if re.search(r"^(hi|hello|hey|yo|namaste)\b", normalized):
            response = "Hello! I'm ASC, your local AI assistant. I'm here to help you with tasks, answer questions, or just have a conversation. What can I do for you today?"
        elif "how are you" in normalized:
            response = "I'm running optimally and ready to assist you. All my core systems are operational. How can I help you today?"
        elif "what can you do" in normalized or "capable" in normalized or "who are you" in normalized:
            response = self._capability_response(context)
        elif "thank" in normalized:
            response = "You're very welcome! I'm always here to help. Is there anything else you'd like me to assist with?"
        else:
            response = "I understand you're asking about that. While my advanced conversational AI is currently unavailable, I can still help you with practical tasks - opening applications, managing files, checking system status, web searches, and more. Just let me know what you need!"

        self._remember(message, response)
        return {
            "success": True,
            "tier": "conversation",
            "mode": "chat",
            "response": response,
            "model": "fallback",
        }

    def _capability_response(self, context: Optional[Dict[str, Any]]) -> str:
        return (
            "I am ASC, your advanced local AI assistant. I can engage in natural conversation, "
            "automate your desktop applications, execute system commands with safety checks, "
            "monitor system resources, manage your files intelligently, navigate and search the web, "
            "assist with form filling using OCR, learn from your preferences, and provide voice interaction. "
            "I'm designed to be your intelligent companion for both conversation and practical tasks."
        )

    def _capability_summary(self, context: Optional[Dict[str, Any]]) -> str:
        tools = (context or {}).get("tools", [])
        if not tools:
            return "- Chat, desktop tools, browser tools, files, system status, and voice diagnostics."
        return "\n".join(f"- {tool['name']}: {tool['description']}" for tool in tools)

    def _remember(self, user: str, assistant: str):
        self.history.append({"user": user, "assistant": assistant})
        self.history = self.history[-self.history_limit:]
