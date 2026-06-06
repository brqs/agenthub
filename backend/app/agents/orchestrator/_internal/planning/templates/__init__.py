"""Legacy template task derivation grouped by delivery type."""

from app.agents.orchestrator._internal.planning.templates.conflicts import (
    workspace_conflict_tasks_from_request,
)
from app.agents.orchestrator._internal.planning.templates.delivery import (
    fullstack_delivery_tasks_from_request,
    preserve_explicit_requirements,
)
from app.agents.orchestrator._internal.planning.templates.legacy import derive_tasks

__all__ = [
    "derive_tasks",
    "fullstack_delivery_tasks_from_request",
    "preserve_explicit_requirements",
    "workspace_conflict_tasks_from_request",
]
