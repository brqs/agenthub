"""Platform-fact classification and rendering."""

from app.agents.orchestrator._internal.routing.platform_facts.classifier import (
    platform_fact_intent,
)
from app.agents.orchestrator._internal.routing.platform_facts.rendering import (
    platform_fact_text,
)

__all__ = ["platform_fact_intent", "platform_fact_text"]
