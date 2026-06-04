"""ReAct decision value types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class ReactDecisionError(ValueError):
    """Raised when ReAct replanner output cannot be safely applied."""


@dataclass(frozen=True, slots=True)
class ReactDecision:
    actions: list[Mapping[str, Any]]
    summary: str = ""
