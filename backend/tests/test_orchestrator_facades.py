"""Stable import-path checks for package facades and service boundaries."""

from importlib import import_module
from importlib.util import find_spec


def test_orchestrator_stable_facades_are_importable() -> None:
    expected_symbols = {
        "app.agents.orchestrator": "OrchestratorAdapter",
        "app.agents.orchestrator.artifacts": "extract_artifact_paths_from_text",
        "app.agents.orchestrator.evaluation": "evaluate_attempt",
        "app.agents.orchestrator.execution": "_run_task",
        "app.agents.orchestrator.planner": "PLANNER_SYSTEM_PROMPT",
        "app.agents.orchestrator.quality": "run_quality_gate",
        "app.agents.orchestrator.task_planning": "resolve_tasks",
        "app.agents.orchestrator.tools": "OrchestratorToolResult",
        "app.agents.orchestrator.types": "SubTask",
        "app.agents.orchestrator.workspace_changes": "refresh_workspace_conflicts",
    }

    for module_name, symbol_name in expected_symbols.items():
        module = import_module(module_name)
        assert hasattr(module, symbol_name), f"{module_name} must export {symbol_name}"


def test_domain_service_packages_are_importable() -> None:
    expected_symbols = {
        "app.services.artifacts.manifest": "ArtifactManifestService",
        "app.services.artifacts.metadata": "build_artifact_metadata",
        "app.services.context.compression": "blocks_to_text",
        "app.services.workspace.container_release": "ContainerDeployWorker",
        "app.services.workspace.deployment_workers": "InProcessContainerDeploymentDispatcher",
        "app.services.workspace.janitor": "WorkspaceResourceJanitor",
        "app.services.workspace.preview_verifier": "BrowserPreviewVerifier",
        "app.services.workspace.static_release": "WorkspaceStaticReleaseService",
        "app.services.workspace.static_server": "SnapshotRequestHandler",
        "app.services.workspace.static_snapshot": "WorkspaceStaticSnapshotService",
    }

    for module_name, symbol_name in expected_symbols.items():
        module = import_module(module_name)
        assert hasattr(module, symbol_name), f"{module_name} must export {symbol_name}"


def test_legacy_flat_service_helper_paths_are_not_facades() -> None:
    service_prefix = "app.services."
    legacy_modules = (
        "artifact_manifest",
        "artifact_metadata",
        "browser_preview_verifier",
        "context_compression",
        "workspace_container_release",
        "workspace_deployment_workers",
        "workspace_janitor",
        "workspace_static_release",
        "workspace_static_server",
        "workspace_static_snapshot",
    )

    for module_name in legacy_modules:
        assert find_spec(f"{service_prefix}{module_name}") is None
