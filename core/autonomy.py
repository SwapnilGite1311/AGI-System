"""
Autonomy engine for phase 3.

The engine is intentionally LLM-optional: it creates executable plans, asks
clarifying questions, and records reasoning using the existing tool/decomposer
layer. Local models can improve this later, but basic autonomy should not
depend on them being online.
"""

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime


class AutonomyEngine:
    """Offline-capable planning and clarification layer."""

    def __init__(self, task_decomposer, tool_manifest_provider: Callable[[], List[Dict[str, Any]]]):
        self.task_decomposer = task_decomposer
        self.tool_manifest_provider = tool_manifest_provider

    def should_handle(self, command: str, complexity: str) -> bool:
        """Return whether the command looks task-oriented and should avoid raw council fallback."""

        normalized = self._normalize(command)
        if not normalized:
            return False

        task_markers = [
            "open", "launch", "start", "search", "find", "look up", "go to", "navigate",
            "fill", "create", "make", "write", "save", "list", "show", "run", "copy",
            "move", "close", "organize", "compare", "backup", "download", "research", "report",
            "analyze", "check", "scan", "status", "process", "file", "folder", "app",
            "duplicates", "disk usage", "network", "environment", "drives",
            "suggest workflows", "suggest automations", "what can you automate",
        ]
        if any(marker in normalized for marker in task_markers):
            return True
        return complexity in {"complex", "critical"}

    def plan(
        self,
        command: str,
        direct_intent: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a phase-3 autonomous plan or a clarification request."""

        normalized = self._normalize(command)
        context = context or {}
        preferences = context.get("preferences", {})
        workflows = context.get("workflow_patterns", [])

        if direct_intent:
            return {
                "mode": "execute",
                "strategy": "direct_intent",
                "confidence": 0.95,
                "reasoning": "A deterministic intent already maps this request to a supported tool.",
                "intent": direct_intent,
            }

        # Proactive assistance - suggest related actions based on context
        proactive_suggestions = self._generate_proactive_suggestions(normalized, context, workflows)
        if proactive_suggestions:
            return {
                "mode": "clarify",
                "strategy": "proactive_assistance",
                "confidence": 0.75,
                "reasoning": "Based on your recent activity, I noticed some related tasks you might want to do.",
                "question": f"I noticed you're working on {self._summarize_context(context)}. Would you like me to help with any of these?",
                "suggestions": proactive_suggestions,
            }

        clarification = self._clarification_for_missing_target(normalized)
        if clarification:
            return clarification

        suggestion_plan = self._workflow_suggestion_plan(normalized, workflows)
        if suggestion_plan:
            return suggestion_plan

        heuristic_plan = self._heuristic_plan(command, normalized, preferences)
        if heuristic_plan:
            return heuristic_plan

        decomposition = self.task_decomposer.decompose(command)
        subtasks = decomposition.get("subtasks", [])
        actionable = [step for step in subtasks if step.get("action") != "general"]
        if actionable:
            decomposition["subtasks"] = actionable
            return {
                "mode": "execute",
                "strategy": decomposition.get("strategy", "decomposed"),
                "confidence": 0.75,
                "reasoning": "The request can be decomposed into supported tool actions.",
                "decomposition": decomposition,
            }

        return {
            "mode": "clarify",
            "strategy": "insufficient_information",
            "confidence": 0.2,
            "question": (
                "I can help with that, but I need a clearer target. "
                "Please mention the app, website, file/folder, command, or output you want."
            ),
            "suggestions": self._tool_suggestions(),
        }

    def _heuristic_plan(self, command: str, normalized: str, preferences: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Infer common flexible requests that are not covered by direct parsing yet."""

        default_browser = self._preference_value(preferences, "default_browser")
        default_notes_folder = self._preference_value(preferences, "notes_folder")

        if normalized in {"open browser", "launch browser", "start browser"}:
            return self._single_step(
                command,
                "open",
                {"app": default_browser or "chrome", "description": command},
                "Open the user's preferred browser when no specific browser is named.",
                confidence=0.86,
            )

        if re.search(
            r"\b(?:open(?:ed)?|running|current(?:ly)?(?:\s+open(?:ed)?)?)\s+(apps|applications|windows)\b",
            normalized,
        ):
            return self._single_step(
                command,
                "process",
                {"description": command},
                "List visible/running applications through the system process tool.",
                confidence=0.78,
            )

        if "disk" in normalized and any(word in normalized for word in ["usage", "space", "storage"]):
            return self._single_step(
                command,
                "status",
                {"description": command},
                "Inspect system status because the user asked about disk/storage.",
                confidence=0.7,
            )

        note_match = re.search(r"(?:make|create|write|save)\s+(?:a\s+)?note\s+(?:about|on)\s+(?P<topic>.+)", normalized)
        if note_match:
            topic = note_match.group("topic").strip(" .")
            filename = f"{self._slugify(topic)}_note.txt"
            note_path = Path(default_notes_folder) / filename if default_notes_folder else Path.cwd() / filename
            return self._single_step(
                command,
                "create_file",
                {
                    "path": str(note_path),
                    "content": f"Notes about {topic}\n",
                    "description": command,
                },
                "Create a note file from a natural language note request.",
                confidence=0.82,
            )

        if normalized in {"help", "what should i try", "what commands can i use"}:
            return {
                "mode": "clarify",
                "strategy": "help",
                "confidence": 0.9,
                "question": "You can ask me to open apps, search websites, manage files, inspect the system, run safe commands, or fill simple forms.",
                "suggestions": self._tool_suggestions(),
            }

        return None

    def _workflow_suggestion_plan(self, normalized: str, workflows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if normalized not in {"suggest workflows", "suggest automations", "what can you automate", "suggest learned workflows"}:
            return None

        suggestions = []
        for workflow in workflows[:5]:
            examples = ", ".join([example for example in workflow.get("examples", []) if example][:2])
            suggestions.append(
                f"{workflow.get('signature')} ({workflow.get('count')} time(s))"
                + (f" e.g. {examples}" if examples else "")
            )

        return {
            "mode": "clarify",
            "strategy": "workflow_suggestions",
            "confidence": 0.9,
            "question": "Here are workflows I can help automate or reuse.",
            "suggestions": suggestions or ["I need more successful task history before I can suggest workflows."],
        }

    def _preference_value(self, preferences: Dict[str, Any], key: str) -> Optional[Any]:
        value = preferences.get(key)
        if isinstance(value, dict):
            return value.get("value")
        return value

    def _single_step(
        self,
        command: str,
        action: str,
        params: Dict[str, Any],
        reasoning: str,
        confidence: float,
    ) -> Dict[str, Any]:
        return {
            "mode": "execute",
            "strategy": "heuristic_single_step",
            "confidence": confidence,
            "reasoning": reasoning,
            "action_plan": [
                {
                    "action": action,
                    "params": params,
                    "description": command,
                }
            ],
        }

    def _generate_proactive_suggestions(self, normalized: str, context: Dict[str, Any], workflows: List[Dict[str, Any]]) -> List[str]:
        """Generate proactive suggestions based on user context and recent activity."""
        suggestions = []
        recent_context = context.get("recent_context", [])
        
        # Analyze recent patterns
        recent_commands = [ctx.get("command", "") for ctx in recent_context]
        
        # If user has been doing file operations, suggest organization
        if any("file" in cmd.lower() or "folder" in cmd.lower() for cmd in recent_commands):
            if "organize" not in " ".join(recent_commands).lower():
                suggestions.append("Would you like me to organize these files by type?")
        
        # If user has been doing web searches, suggest related actions
        if any("search" in cmd.lower() or "open" in cmd.lower() for cmd in recent_commands):
            if "note" not in " ".join(recent_commands).lower():
                suggestions.append("Would you like me to take notes on what you found?")
        
        # If user has been doing system checks, suggest optimization
        if any("system" in cmd.lower() or "status" in cmd.lower() for cmd in recent_commands):
            if len(recent_commands) >= 2:
                suggestions.append("Would you like me to analyze your system performance?")
        
        # Workflow-based suggestions
        for workflow in workflows[:3]:
            signature = workflow.get("signature", "")
            if signature and "web" in signature.lower() and "file" not in normalized:
                suggestions.append(f"I noticed you often {signature.replace('workflow:', '')}. Would you like me to help with that?")
        
        return suggestions[:3] if suggestions else []

    def _summarize_context(self, context: Dict[str, Any]) -> str:
        """Summarize current user context for proactive suggestions."""
        recent_context = context.get("recent_context", [])
        if not recent_context:
            return "general tasks"
        
        recent_commands = [ctx.get("command", "") for ctx in recent_context]
        if not recent_commands:
            return "general tasks"
        
        # Detect dominant activity type
        web_count = sum(1 for cmd in recent_commands if any(word in cmd.lower() for word in ["search", "open", "browser", "chrome", "google"]))
        file_count = sum(1 for cmd in recent_commands if any(word in cmd.lower() for word in ["file", "folder", "organize", "desktop", "documents"]))
        system_count = sum(1 for cmd in recent_commands if any(word in cmd.lower() for word in ["system", "status", "process", "cpu", "ram"]))
        
        if web_count >= file_count and web_count >= system_count:
            return "web research"
        elif file_count >= web_count and file_count >= system_count:
            return "file management"
        elif system_count >= web_count and system_count >= file_count:
            return "system monitoring"
        else:
            return "various tasks"

    def _clarification_for_missing_target(self, normalized: str) -> Optional[Dict[str, Any]]:
        if re.fullmatch(r"(open|launch|start|search|find|look up|go to|navigate|fill|create|make|copy|move|delete|organize|run)", normalized):
            verb = normalized.split()[0]
            return {
                "mode": "clarify",
                "strategy": "missing_target",
                "confidence": 0.95,
                "question": f"What should I {verb}? Please give me the target or details.",
                "suggestions": self._tool_suggestions(),
            }

        if re.search(r"\b(it|that|there)\b", normalized) and not any(
            site in normalized for site in ["amazon", "google", "youtube", "github", "flipkart"]
        ):
            return {
                "mode": "clarify",
                "strategy": "ambiguous_reference",
                "confidence": 0.8,
                "question": "What does that refer to? I need the specific app, site, file, or folder.",
                "suggestions": self._tool_suggestions(),
            }

        if "create file" in normalized and not re.search(r"(?:named|called)\s+\S+", normalized):
            return {
                "mode": "clarify",
                "strategy": "missing_filename",
                "confidence": 0.85,
                "question": "What should I name the file?",
                "suggestions": ["create file named notes.txt"],
            }

        return None

    def _tool_suggestions(self) -> List[str]:
        tools = self.tool_manifest_provider()
        suggestions = []
        for tool in tools:
            actions = ", ".join(tool.get("actions", [])[:4])
            suggestions.append(f"{tool.get('name')}: {actions}")
        return suggestions[:6]

    def _normalize(self, command: str) -> str:
        return " ".join((command or "").lower().strip().split())

    def _slugify(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "note"
