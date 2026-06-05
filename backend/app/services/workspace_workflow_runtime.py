"""No-side-effect workflow dry-run runtime for workspace workflow artifacts."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace, WorkspaceWorkflowRun
from app.services.workspace_service import WorkspaceService

MAX_WORKFLOW_NODES = 50
MAX_WORKFLOW_EDGES = 100
SUPPORTED_NODE_TYPES = {"trigger", "task", "assert", "end"}


class WorkflowRunNotFoundError(RuntimeError):
    """Raised when a workflow dry-run record cannot be found."""


class WorkflowRuntimeError(RuntimeError):
    """Raised when a workflow cannot be dry-run by the local runtime."""


class WorkspaceWorkflowRuntimeService:
    """Validate and dry-run workflow artifacts without shell/network side effects."""

    def __init__(self, workspace_service: WorkspaceService | None = None) -> None:
        self._workspace_service = workspace_service or WorkspaceService()

    async def dry_run(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        *,
        path: str,
        inputs: dict[str, Any] | None = None,
    ) -> WorkspaceWorkflowRun:
        workspace = await self._workspace_service.get_or_create(db, conversation_id)
        normalized_path, definition = self._load_definition(workspace, path)
        result = self._execute(definition, inputs or {})
        now = datetime.now(UTC)
        run = WorkspaceWorkflowRun(
            conversation_id=conversation_id,
            workspace_id=workspace.id,
            path=normalized_path,
            mode="dry_run",
            status=result["status"],
            validation_status=result["validation_status"],
            runtime_status=result["runtime_status"],
            dry_run_status=result["dry_run_status"],
            health_status=result["health_status"],
            inputs=deepcopy(inputs or {}),
            definition=definition,
            context=result["context"],
            node_results=result["node_results"],
            error=result.get("error"),
            completed_at=now,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run

    async def list_runs(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        *,
        path: str | None = None,
        limit: int = 20,
    ) -> list[WorkspaceWorkflowRun]:
        stmt = (
            select(WorkspaceWorkflowRun)
            .where(WorkspaceWorkflowRun.conversation_id == conversation_id)
            .order_by(WorkspaceWorkflowRun.created_at.desc())
            .limit(limit)
        )
        if path:
            stmt = stmt.where(WorkspaceWorkflowRun.path == path)
        return list((await db.execute(stmt)).scalars().all())

    async def get_run(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        run_id: UUID,
    ) -> WorkspaceWorkflowRun:
        stmt = select(WorkspaceWorkflowRun).where(
            WorkspaceWorkflowRun.conversation_id == conversation_id,
            WorkspaceWorkflowRun.id == run_id,
        )
        run = (await db.execute(stmt)).scalar_one_or_none()
        if run is None:
            raise WorkflowRunNotFoundError("workflow run not found")
        return run

    async def latest_run(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        *,
        path: str,
    ) -> WorkspaceWorkflowRun | None:
        stmt = (
            select(WorkspaceWorkflowRun)
            .where(
                WorkspaceWorkflowRun.conversation_id == conversation_id,
                WorkspaceWorkflowRun.path == path,
            )
            .order_by(WorkspaceWorkflowRun.created_at.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def health(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        *,
        path: str,
    ) -> tuple[str, str, str, str, WorkspaceWorkflowRun | None]:
        latest = await self.latest_run(db, conversation_id, path=path)
        if latest is not None:
            return (
                latest.validation_status,
                latest.runtime_status,
                latest.dry_run_status,
                latest.health_status,
                latest,
            )
        return ("unknown", "not_supported", "not_supported", "unknown", None)

    async def enrich_workflow_blocks(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        blocks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for block in blocks:
            if block.get("type") != "workflow" or not isinstance(block.get("path"), str):
                enriched.append(block)
                continue
            latest = await self.latest_run(db, conversation_id, path=block["path"])
            if latest is None:
                enriched.append(block)
                continue
            updated = dict(block)
            updated["last_run_id"] = str(latest.id)
            updated["validation_status"] = latest.validation_status
            updated["runtime_status"] = latest.runtime_status
            updated["dry_run_status"] = latest.dry_run_status
            updated["health_status"] = latest.health_status
            enriched.append(updated)
        return enriched

    def _load_definition(self, workspace: Workspace, path: str) -> tuple[str, dict[str, Any]]:
        target = self._workspace_service.validate_read_path(Path(workspace.root_path), path)
        raw = target.read_text(encoding="utf-8")
        payload = _parse_workflow(raw, target.suffix.lower())
        normalized = target.relative_to(Path(workspace.root_path)).as_posix()
        if not isinstance(payload, dict):
            raise WorkflowRuntimeError("workflow definition must be an object")
        return normalized, payload

    def _execute(self, definition: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
        validation_error = _schema_error(definition)
        if validation_error:
            return _failed_result(
                definition,
                inputs,
                validation_status="failed",
                runtime_status="invalid",
                error=validation_error,
            )
        runtime_error = _runtime_error(definition)
        if runtime_error:
            return _failed_result(
                definition,
                inputs,
                validation_status="passed",
                runtime_status="invalid",
                error=runtime_error,
            )
        not_supported_reason = _not_supported_reason(definition)
        if not_supported_reason:
            return _not_supported_result(definition, inputs, reason=not_supported_reason)

        nodes = _node_map(definition)
        edges = _edges(definition)
        order_error, order = _topological_order(nodes, edges)
        if order_error:
            return _failed_result(
                definition,
                inputs,
                validation_status="passed",
                runtime_status="invalid",
                error=order_error,
            )

        context = deepcopy(inputs)
        node_results: list[dict[str, Any]] = []
        failed_node_ids: set[str] = set()
        upstream_by_target = _upstream_by_target(edges)

        for node_id in order:
            node = nodes[node_id]
            blocked = sorted(upstream_by_target.get(node_id, set()) & failed_node_ids)
            if blocked:
                failed_node_ids.add(node_id)
                node_results.append(
                    _node_result(
                        node_id,
                        node,
                        "skipped",
                        f"Skipped because upstream node failed: {', '.join(blocked)}.",
                    )
                )
                continue
            result = _execute_node(node, context)
            node_results.append(result)
            if result["status"] != "passed":
                failed_node_ids.add(node_id)

        passed = all(result["status"] == "passed" for result in node_results)
        return {
            "status": "passed" if passed else "failed",
            "validation_status": "passed",
            "runtime_status": "ready" if passed else "invalid",
            "dry_run_status": "passed" if passed else "failed",
            "health_status": "passed" if passed else "failed",
            "context": _json_safe(context),
            "node_results": node_results,
            "error": None if passed else "workflow dry-run failed",
        }


def _parse_workflow(raw: str, suffix: str) -> Any:
    try:
        if suffix == ".json" or raw.lstrip().startswith("{"):
            return json.loads(raw)
        yaml = import_module("yaml")
        return yaml.safe_load(raw)
    except Exception as exc:  # noqa: BLE001
        raise WorkflowRuntimeError(f"failed to parse workflow definition: {exc}") from exc


def _schema_error(definition: Mapping[str, Any]) -> str | None:
    for key in ("version", "name", "nodes", "edges"):
        if key not in definition:
            return f"workflow missing required field: {key}"
    nodes = definition.get("nodes")
    edges = definition.get("edges")
    if not isinstance(nodes, list) or not nodes:
        return "workflow nodes must be a non-empty list"
    if len(nodes) > MAX_WORKFLOW_NODES:
        return f"workflow has too many nodes: {len(nodes)} > {MAX_WORKFLOW_NODES}"
    if not isinstance(edges, list):
        return "workflow edges must be a list"
    if len(edges) > MAX_WORKFLOW_EDGES:
        return f"workflow has too many edges: {len(edges)} > {MAX_WORKFLOW_EDGES}"
    seen: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping):
            return f"workflow node {index} must be an object"
        node_id = node.get("id")
        node_type = node.get("type")
        if not isinstance(node_id, str) or not node_id.strip():
            return f"workflow node {index} must have a string id"
        if node_id in seen:
            return f"workflow duplicate node id: {node_id}"
        seen.add(node_id)
        if not isinstance(node_type, str) or not node_type.strip():
            return f"workflow node {node_id} must have a string type"
    for index, edge in enumerate(edges):
        if not isinstance(edge, Mapping):
            return f"workflow edge {index} must be an object"
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, str) or source not in seen:
            return f"workflow edge {index} references missing source node"
        if not isinstance(target, str) or target not in seen:
            return f"workflow edge {index} references missing target node"
    return None


def _runtime_error(definition: Mapping[str, Any]) -> str | None:
    nodes = definition.get("nodes")
    assert isinstance(nodes, list)
    for node in nodes:
        assert isinstance(node, Mapping)
        node_type = str(node["type"])
        if node_type == "action":
            continue
        if node_type not in SUPPORTED_NODE_TYPES:
            return f"unsupported workflow node type: {node_type}"
        if node_type == "task" and _task_action(node) != "set_context":
            return f"unsupported workflow task action: {_task_action(node) or '<missing>'}"
    return None


def _not_supported_reason(definition: Mapping[str, Any]) -> str | None:
    nodes = definition.get("nodes")
    assert isinstance(nodes, list)
    for node in nodes:
        assert isinstance(node, Mapping)
        if str(node["type"]) == "action":
            # not_supported means external-runtime-required, not deterministic failure.
            return "workflow action nodes require a non-local runtime"
    return None


def _node_map(definition: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    nodes = definition.get("nodes")
    assert isinstance(nodes, list)
    return {str(node["id"]): node for node in nodes if isinstance(node, Mapping)}


def _edges(definition: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    edges = definition.get("edges")
    assert isinstance(edges, list)
    return [edge for edge in edges if isinstance(edge, Mapping)]


def _topological_order(
    nodes: Mapping[str, Mapping[str, Any]],
    edges: list[Mapping[str, Any]],
) -> tuple[str | None, list[str]]:
    indegree = dict.fromkeys(nodes, 0)
    downstream: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for edge in edges:
        source = str(edge["source"])
        target = str(edge["target"])
        downstream[source].add(target)
        indegree[target] += 1
    queue = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
    order: list[str] = []
    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for target in sorted(downstream[node_id]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(order) != len(nodes):
        return "workflow graph contains a cycle", order
    return None, order


def _upstream_by_target(edges: list[Mapping[str, Any]]) -> dict[str, set[str]]:
    upstream: dict[str, set[str]] = {}
    for edge in edges:
        upstream.setdefault(str(edge["target"]), set()).add(str(edge["source"]))
    return upstream


def _execute_node(node: Mapping[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node["id"])
    node_type = str(node["type"])
    if node_type in {"trigger", "end"}:
        return _node_result(node_id, node, "passed", f"{node_type} passed.")
    if node_type == "task":
        values = _task_values(node)
        _deep_merge(context, values)
        return _node_result(
            node_id,
            node,
            "passed",
            "set_context applied.",
            outputs=values,
        )
    if node_type == "assert":
        equals = _assert_equals(node)
        mismatches = [
            f"{path}: expected {expected!r}, got {_get_path(context, path)!r}"
            for path, expected in equals.items()
            if _get_path(context, path) != expected
        ]
        if mismatches:
            return _node_result(node_id, node, "failed", "; ".join(mismatches))
        return _node_result(node_id, node, "passed", "assertions passed.")
    return _node_result(node_id, node, "failed", f"unsupported node type: {node_type}")


def _task_action(node: Mapping[str, Any]) -> str | None:
    config = node.get("config")
    if not isinstance(config, Mapping):
        return None
    action = config.get("action")
    return action if isinstance(action, str) else None


def _task_values(node: Mapping[str, Any]) -> dict[str, Any]:
    config = node.get("config")
    if not isinstance(config, Mapping):
        return {}
    values = config.get("values")
    return deepcopy(values) if isinstance(values, dict) else {}


def _assert_equals(node: Mapping[str, Any]) -> dict[str, Any]:
    config = node.get("config")
    if not isinstance(config, Mapping):
        return {}
    equals = config.get("equals")
    return dict(equals) if isinstance(equals, Mapping) else {}


def _node_result(
    node_id: str,
    node: Mapping[str, Any],
    status: str,
    message: str,
    *,
    outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "node_id": node_id,
        "type": str(node.get("type") or ""),
        "status": status,
        "message": message,
    }
    if outputs:
        result["outputs"] = _json_safe(outputs)
    return result


def _deep_merge(target: dict[str, Any], values: Mapping[str, Any]) -> None:
    for key, value in values.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)


def _get_path(context: Mapping[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _failed_result(
    definition: dict[str, Any],
    inputs: dict[str, Any],
    *,
    validation_status: str,
    runtime_status: str,
    error: str,
) -> dict[str, Any]:
    node_results = [
        _node_result(str(node.get("id") or index), node, "skipped", error)
        for index, node in enumerate(definition.get("nodes") or [])
        if isinstance(node, Mapping)
    ]
    return {
        "status": "failed",
        "validation_status": validation_status,
        "runtime_status": runtime_status,
        "dry_run_status": "failed",
        "health_status": "failed",
        "context": _json_safe(inputs),
        "node_results": node_results,
        "error": error,
    }


def _not_supported_result(
    definition: dict[str, Any],
    inputs: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    node_results = [
        _node_result(str(node.get("id") or index), node, "skipped", reason)
        for index, node in enumerate(definition.get("nodes") or [])
        if isinstance(node, Mapping)
    ]
    return {
        "status": "passed",
        "validation_status": "passed",
        "runtime_status": "ready",
        "dry_run_status": "not_supported",
        "health_status": "passed",
        "context": _json_safe(inputs),
        "node_results": node_results,
        "error": None,
    }


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))
