"""Legacy template task derivation grouped by delivery type."""

from app.agents.orchestrator._internal.planning.templates.conflicts import (
    workspace_conflict_tasks_from_request,
)
from app.agents.orchestrator._internal.planning.templates.delivery import (
    frontend_deploy_tasks_from_request,
    fullstack_delivery_tasks_from_request,
    preserve_explicit_requirements,
    stabilize_frontend_deploy_tasks,
)
from app.agents.orchestrator._internal.planning.templates.legacy import derive_tasks

__all__ = [
    "derive_tasks",
    "frontend_deploy_tasks_from_request",
    "fullstack_delivery_tasks_from_request",
    "preserve_explicit_requirements",
    "stabilize_frontend_deploy_tasks",
    "workspace_conflict_tasks_from_request",
]
