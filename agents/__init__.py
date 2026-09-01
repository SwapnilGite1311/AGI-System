"""Agent package exports for ASC.

Imported lazily (PEP 562). Eagerly importing all five agents here meant
that touching any one of them pulled in `learning_agent`, which pulls in
`phase5_model` -> `neural_command_model` -> torch, and separately sklearn.
That was 16 seconds of import before the first command could even be
parsed, on every startup, whether or not the learning path was ever used.

`from agents import FileAgent` and `from agents.file_agent import FileAgent`
both still work; the cost is now paid only by whoever actually asks for the
agent that needs it.
"""

from importlib import import_module
from typing import TYPE_CHECKING

_EXPORTS = {
    "FileAgent": ".file_agent",
    "LearningAgent": ".learning_agent",
    "SystemAgent": ".system_agent",
    "VisionAgent": ".vision_agent",
    "WebAgent": ".web_agent",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value  # cache, so this runs once per name
    return value


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))


if TYPE_CHECKING:  # for type checkers and IDEs only - never at runtime
    from .file_agent import FileAgent
    from .learning_agent import LearningAgent
    from .system_agent import SystemAgent
    from .vision_agent import VisionAgent
    from .web_agent import WebAgent
