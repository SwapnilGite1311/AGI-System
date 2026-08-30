"""
Which route the neural model is expected to predict for a given intent.

Deliberately delegates to the model's own `_route_from_intent` rather than
restating the mapping here. A benchmark that keeps its own copy of the
system's logic ends up measuring whether the two copies agree, which is not
the question being asked.
"""

from functools import lru_cache
from typing import Optional


@lru_cache(maxsize=1)
def _mapper():
    from learning.neural_command_model import NeuralCommandModel

    model = NeuralCommandModel.__new__(NeuralCommandModel)
    return model._route_from_intent


def route_for(intent_type: str) -> Optional[str]:
    """The route label the model should emit for this intent type."""
    try:
        return _mapper()(intent_type)
    except Exception:
        return None
