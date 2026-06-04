"""Public compatibility facade for Orchestrator structured memory."""

from app.services._orchestrator_memory.capability_v1 import (
    build_agent_capability_profile,
)
from app.services._orchestrator_memory.capability_v2 import (
    build_agent_capability_profile_v2,
)
from app.services._orchestrator_memory.context import (
    build_orchestrator_memory_context,
    inject_orchestrator_memory_context,
)
from app.services._orchestrator_memory.run_reader import (
    get_orchestrator_run_detail,
    list_orchestrator_runs,
)
from app.services._orchestrator_memory.store import OrchestratorMemoryStore
from app.services._orchestrator_memory.types import (
    DEFAULT_ORCHESTRATOR_MEMORY_CONTEXT_MAX_CHARS,
    DEFAULT_ORCHESTRATOR_MEMORY_RECENT_RUNS,
    AgentCapabilityProfileItem,
    AgentCapabilityProfileV2,
    AgentCapabilityProfileV2Item,
    UserPreferenceMemory,
)

__all__ = [
    "AgentCapabilityProfileItem",
    "AgentCapabilityProfileV2",
    "AgentCapabilityProfileV2Item",
    "DEFAULT_ORCHESTRATOR_MEMORY_CONTEXT_MAX_CHARS",
    "DEFAULT_ORCHESTRATOR_MEMORY_RECENT_RUNS",
    "OrchestratorMemoryStore",
    "UserPreferenceMemory",
    "build_agent_capability_profile",
    "build_agent_capability_profile_v2",
    "build_orchestrator_memory_context",
    "get_orchestrator_run_detail",
    "inject_orchestrator_memory_context",
    "list_orchestrator_runs",
]
