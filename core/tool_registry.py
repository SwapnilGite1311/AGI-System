"""
Tool registry for ASC agent actions.

This keeps executable capabilities explicit and inspectable so the planner can
choose tools instead of relying on a growing chain of command-specific branches.
"""

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional


ToolHandler = Callable[[str, Dict[str, Any], str], Dict[str, Any] | Awaitable[Dict[str, Any]]]


@dataclass
class ToolSpec:
    """Metadata and executable handler for one ASC tool."""

    name: str
    agent: str
    description: str
    actions: List[str]
    handler: ToolHandler
    required_params: List[str] = field(default_factory=list)

    def manifest(self) -> Dict[str, Any]:
        """Return planner-safe tool metadata."""

        return {
            "name": self.name,
            "agent": self.agent,
            "description": self.description,
            "actions": self.actions,
            "required_params": self.required_params,
        }


class ToolRegistry:
    """Registers and executes named/aliased ASC tools."""

    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}
        self._action_index: Dict[str, str] = {}

    def register(self, spec: ToolSpec):
        """Register a tool and all supported action aliases."""

        self._tools[spec.name] = spec
        for action in spec.actions:
            self._action_index[action.lower()] = spec.name

    def resolve(self, action: str) -> Optional[ToolSpec]:
        """Resolve an action alias to a registered tool."""

        return self._tools.get(self._action_index.get((action or "").lower(), ""))

    def manifest(self) -> List[Dict[str, Any]]:
        """Return all tool metadata for planners and diagnostics."""

        return [tool.manifest() for tool in self._tools.values()]

    async def execute(self, action: str, params: Dict[str, Any], context: str) -> Dict[str, Any]:
        """Execute a registered tool by action alias."""

        spec = self.resolve(action)
        if not spec:
            return {
                "success": False,
                "action": action,
                "error": f"No registered tool can handle action '{action}'.",
            }

        missing = [key for key in spec.required_params if not params.get(key)]
        if missing:
            return {
                "success": False,
                "action": action,
                "agent": spec.agent,
                "tool": spec.name,
                "error": f"Missing required parameter(s): {', '.join(missing)}",
            }

        try:
            result = spec.handler(action, params, context)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            return {
                "success": False,
                "action": action,
                "agent": spec.agent,
                "tool": spec.name,
                "error": str(exc),
            }

        if not isinstance(result, dict):
            return {
                "success": False,
                "action": action,
                "agent": spec.agent,
                "tool": spec.name,
                "error": f"Tool returned unsupported result type: {type(result).__name__}",
            }

        result.setdefault("action", action)
        result.setdefault("agent", spec.agent)
        result.setdefault("tool", spec.name)
        return result
