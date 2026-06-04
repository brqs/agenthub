"""Workflow artifact evaluator."""

from __future__ import annotations

from collections.abc import Mapping

from app.agents.orchestrator._internal.evaluation.artifacts.common import (
    _failed,
    _load_structured_payload,
)
from app.agents.orchestrator._internal.evaluation.types import EvaluationIssue, EvaluationResult


def evaluate_workflow_artifact(path: str, suffix: str, text: str) -> EvaluationResult:
    payload = _load_structured_payload(path, suffix, text, "workflow_validation")
    if isinstance(payload, EvaluationResult):
        return payload
    issues: list[EvaluationIssue] = []
    if not isinstance(payload, Mapping):
        issues.append(
            EvaluationIssue(
                code="workflow_not_object",
                message=f"{path} must be an object with version, name, nodes, and edges.",
                evidence=path,
                repair_hint="Use a JSON/YAML object containing version, name, nodes, and edges.",
            )
        )
        return _failed("workflow_validation", [path], issues)

    for key in ("version", "name", "nodes", "edges"):
        if key not in payload:
            issues.append(
                EvaluationIssue(
                    code=f"workflow_missing_{key}",
                    message=f"{path} is missing required workflow field '{key}'.",
                    evidence=path,
                    repair_hint=f"Add the '{key}' field to the workflow artifact.",
                )
            )
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    node_ids: set[str] = set()
    if not isinstance(nodes, list) or not nodes:
        issues.append(
            EvaluationIssue(
                code="workflow_nodes_invalid",
                message=f"{path} must define a non-empty nodes list.",
                evidence=path,
                repair_hint="Add nodes with string id and type fields.",
            )
        )
    else:
        for index, node in enumerate(nodes):
            if not isinstance(node, Mapping):
                issues.append(
                    EvaluationIssue(
                        code="workflow_node_not_object",
                        message=f"{path} node {index} must be an object.",
                        evidence=f"nodes[{index}]",
                        repair_hint="Represent each workflow node as an object.",
                    )
                )
                continue
            node_id = node.get("id")
            node_type = node.get("type")
            if not isinstance(node_id, str) or not node_id.strip():
                issues.append(
                    EvaluationIssue(
                        code="workflow_node_missing_id",
                        message=f"{path} node {index} is missing a string id.",
                        evidence=f"nodes[{index}]",
                        repair_hint="Give every node a unique string id.",
                    )
                )
                continue
            if node_id in node_ids:
                issues.append(
                    EvaluationIssue(
                        code="workflow_duplicate_node_id",
                        message=f"{path} contains duplicate node id '{node_id}'.",
                        evidence=node_id,
                        repair_hint="Make workflow node ids unique.",
                    )
                )
            node_ids.add(node_id)
            if not isinstance(node_type, str) or not node_type.strip():
                issues.append(
                    EvaluationIssue(
                        code="workflow_node_missing_type",
                        message=f"{path} node '{node_id}' is missing a string type.",
                        evidence=node_id,
                        repair_hint="Give every node a string type.",
                    )
                )
    if not isinstance(edges, list):
        issues.append(
            EvaluationIssue(
                code="workflow_edges_invalid",
                message=f"{path} must define an edges list.",
                evidence=path,
                repair_hint="Add an edges list, using [] when there are no edges.",
            )
        )
    else:
        for index, edge in enumerate(edges):
            if not isinstance(edge, Mapping):
                issues.append(
                    EvaluationIssue(
                        code="workflow_edge_not_object",
                        message=f"{path} edge {index} must be an object.",
                        evidence=f"edges[{index}]",
                        repair_hint="Represent each workflow edge as an object.",
                    )
                )
                continue
            source = edge.get("source")
            target = edge.get("target")
            if not isinstance(source, str) or source not in node_ids:
                issues.append(
                    EvaluationIssue(
                        code="workflow_dangling_edge_source",
                        message=f"{path} edge {index} references missing source node.",
                        evidence=str(source),
                        repair_hint="Point every edge source at an existing node id.",
                    )
                )
            if not isinstance(target, str) or target not in node_ids:
                issues.append(
                    EvaluationIssue(
                        code="workflow_dangling_edge_target",
                        message=f"{path} edge {index} references missing target node.",
                        evidence=str(target),
                        repair_hint="Point every edge target at an existing node id.",
                    )
                )
    if issues:
        return _failed("workflow_validation", [path], issues)
    return EvaluationResult(
        evaluator="workflow_validation",
        status="passed",
        passed=True,
        checked_artifacts=[path],
    )
