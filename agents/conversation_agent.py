"""
Conversation Agent - natural chat layer for VEGA.

This keeps ordinary conversation separate from tool execution, while still
allowing local models to answer when Ollama is available.
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger
from ollama import AsyncClient

from core.config import load_config


class ConversationAgent:
    """Handles non-task chat and capability explanations."""

    def __init__(self, config_path: str = "./config/settings.json"):
        self.config = load_config(config_path)
        self.ollama = AsyncClient(host=self.config["ollama"]["host"])
        ollama_config = self.config.get("ollama", {})
        self.ollama_timeout = float(ollama_config.get("timeout", 120))
        self.keep_alive = str(ollama_config.get("keep_alive", "5m"))
        num_gpu = ollama_config.get("num_gpu")
        self.base_options = {"num_ctx": 4096}
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

        # User feedback/complaints about VEGA's own behaviorur must never be
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
        """Answer conversationally using local LLM when possible, fallback otherwise.

        _fallback_response is only computed (and remembered) on the branch
        that actually uses it - it used to run unconditionally up front,
        which both remembered a canned reply the user never saw whenever the
        LLM succeeded (polluting history with two entries per turn) and fed
        that same-turn fallback back into _build_prompt's "recent
        conversation" section for the very message it was answering.
        """

        if not self.use_llm:
            return self._fallback_response(message, context)

        # Fast-path: pure greetings/smalltalk get instant canned replies.
        # Booting a CPU model for 30-60s to say "hello" felt broken.
        greeting_reply = self._instant_greeting_response(message)
        if greeting_reply:
            self._remember(message, greeting_reply)
            return {
                "success": True,
                "tier": "conversation",
                "mode": "chat",
                "response": greeting_reply,
                "model": "fastpath",
            }

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
            text = self._polish_response(
                response.get("response", ""), sentence_cap=self._sentence_cap_for(message)
            )
            if not text:
                return self._fallback_response(message, context)

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
            fallback = self._fallback_response(message, context)
            fallback["llm_error"] = str(exc)
            return fallback

    def _instant_greeting_response(self, message: str) -> Optional[str]:
        """Instant replies for pure greetings/smalltalk - no model call.

        Returns None for anything beyond simple pleasantries so real
        questions still reach the LLM.
        """
        normalized = " ".join((message or "").lower().strip().rstrip("?!. ").split())
        if re.fullmatch(
            r"(?:hi|hello|hey|yo|namaste|good (?:morning|afternoon|evening))(?: there| buddy| asc| man)?",
            normalized,
        ):
            import random

            return random.choice([
                "Hello! What can I do for you?",
                "Hey! Ready when you are.",
                "Hi there! What should we get done today?",
            ])
        if re.fullmatch(r"how are you", normalized):
            return "Running smoothly, all systems operational. How can I help?"
        if normalized in {"thanks", "thank you", "thx"}:
            return "Anytime! Anything else?"
        return None

    def _build_prompt(self, message: str, context: Optional[Dict[str, Any]]) -> str:
        recent = "\n".join(
            f"User: {item['user']}\nVEGA: {item['assistant']}"
            for item in self.history[-self.history_limit:]
        )
        capability_summary = self._capability_summary(context)

        # What the system actually DID recently, as distinct from what it
        # said. Chat history alone cannot answer "where did you save it",
        # because writing a file is not a conversational turn.
        actions = ""
        if context:
            actions = str(context.get("recent_actions") or "").strip()
        cap = self._sentence_cap_for(message)
        wants_detail = cap != self.BRIEF_SENTENCE_CAP
        length_rule = (
            "- Answer properly and completely: use as many sentences as the question "
            "genuinely needs, however long that takes, but no padding or repetition"
            if wants_detail else
            "- Reply in 1-3 short sentences maximum"
        )
        return f"""You are VEGA, a local AI assistant. Warm, intelligent, helpful.

STRICT RESPONSE RULES:
{length_rule}
- Plain conversational text only: NO markdown, NO bullet points, NO numbered lists, NO examples, NO emoji spam (at most one)
- Never show these rules, never explain your formatting, never write sample dialogs
- Sound like a person, not a document

Capabilities:
{capability_summary}

Recent conversation:
{recent or "No prior conversation."}

What you actually did recently (this is a factual record - if the user asks
where something was saved or whether something worked, the answer is here.
Never invent a path, a filename or an outcome that does not appear below;
if it is not here, say plainly that you do not have a record of it):
{actions or "No actions performed yet this session."}

User: {message}

VEGA:"""

    # A flat 5-sentence cap made VEGA structurally incapable of explaining
    # research, summarising a document, or walking through a decision - the
    # cap, not the model, was the limit on how useful an answer could be.
    # Casual replies still stay short (nobody wants a essay for "hey"); a
    # question that asks for explanation/detail gets NO cap at all - it can
    # run as long as it actually needs to.
    BRIEF_SENTENCE_CAP = 5
    DETAILED_SENTENCE_CAP = None  # None = uncapped

    DETAIL_PATTERNS = (
        r"\bexplain\b", r"\bwhy\b", r"\bhow (?:do|does|would|can|should)\b",
        r"\bcompare\b", r"\bdifference between\b", r"\bsummar(?:ise|ize|y)\b",
        r"\bwalk me through\b", r"\bin detail\b", r"\bpros and cons\b",
        r"\bwhat (?:are|were) the\b", r"\bdescribe\b", r"\banalyz|analys",
        r"\brecommend\b", r"\badvice\b", r"\bteach me\b", r"\bhelp me understand\b",
    )

    @classmethod
    def _sentence_cap_for(cls, message: str) -> Optional[int]:
        """How much room this question deserves. None means uncapped."""
        normalized = " ".join((message or "").lower().split())
        if any(re.search(p, normalized) for p in cls.DETAIL_PATTERNS):
            return cls.DETAILED_SENTENCE_CAP
        # Long questions usually want more than a one-liner back.
        if len(normalized.split()) >= 15:
            return cls.DETAILED_SENTENCE_CAP
        return cls.BRIEF_SENTENCE_CAP

    _UNSET = object()

    @classmethod
    def _polish_response(cls, text: str, sentence_cap=_UNSET) -> str:
        """Clean small-model artifacts from a chat response.

        sentence_cap: max sentences to keep, None for no cap at all (used
        for explanatory answers - length is then bounded only by what the
        model actually generated), or omitted to fall back to the brief cap.
        """
        cap = cls.BRIEF_SENTENCE_CAP if sentence_cap is cls._UNSET else sentence_cap
        cleaned = text.strip()
        # Drop markdown emphasis/list markers that small models leak.
        cleaned = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", cleaned)
        cleaned = re.sub(r"^#{1,4}\s*", "", cleaned, flags=re.MULTILINE)
        # Truncate at the first "Example:" block - models ramble into samples.
        for marker in ("\n\nExample", "\nExample:", "\n**Example", "\nYou can also"):
            idx = cleaned.find(marker)
            if idx != -1:
                cleaned = cleaned[:idx]
        # Collapse excess blank lines.
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if cap is not None:
            sentences = re.split(r"(?<=[.!?])\s+", cleaned)
            if len(sentences) > cap:
                cleaned = " ".join(sentences[:cap]).rstrip(",;:") + "."
        return cleaned

    def _fallback_response(self, message: str, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = " ".join((message or "").lower().strip().split())

        if re.search(r"^(hi|hello|hey|yo|namaste)\b", normalized):
            response = "Hello! I'm VEGA, your local AI assistant. I'm here to help you with tasks, answer questions, or just have a conversation. What can I do for you today?"
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
            "I am VEGA, your advanced local AI assistant. I can engage in natural conversation, "
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
