"""Pure acceptance evaluators.

Runners collect API evidence into the report first. Evaluators only inspect and
update that report, which keeps acceptance semantics easy to unit test.
"""

from __future__ import annotations

from typing import Any

from . import runner as legacy


def _content_blocks(report: dict[str, Any]) -> list[dict[str, Any]]:
    target = report.get("target_agent_message")
    if not isinstance(target, dict):
        return []
    blocks = target.get("content")
    return blocks if isinstance(blocks, list) else []


def _artifacts(report: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = report.get("workspace_artifacts_api")
    return artifacts if isinstance(artifacts, list) else []


def evaluate_p1_rich_artifacts(report: dict[str, Any]) -> None:
    file_blocks = [block for block in _content_blocks(report) if block.get("type") == "file"]
    artifacts = _artifacts(report)
    report["rich_artifact_file_blocks"] = file_blocks
    required_kinds = {"document", "ppt", "image", "archive"}
    block_kinds = {str(block.get("artifact_kind")) for block in file_blocks}
    manifest_kinds = {str(item.get("artifact_kind")) for item in artifacts}
    manifest_by_path = {
        str(item.get("path")): item
        for item in artifacts
        if isinstance(item.get("path"), str)
    }
    aligned_blocks = []
    for block in file_blocks:
        path = block.get("path")
        manifest = manifest_by_path.get(path) if isinstance(path, str) else None
        aligned_blocks.append(
            bool(
                manifest
                and manifest.get("artifact_kind") == block.get("artifact_kind")
                and manifest.get("agent_id") == block.get("agent_id")
            )
        )
    checks = report.setdefault("checks", {})
    checks["p1_rich_artifacts_file_blocks_present"] = required_kinds.issubset(block_kinds)
    checks["p1_rich_artifacts_manifest_present"] = required_kinds.issubset(manifest_kinds)
    checks["p1_rich_artifacts_block_manifest_aligned"] = bool(aligned_blocks) and all(
        aligned_blocks
    )
    checks["p1_rich_artifacts_manifest_has_task_run_agent"] = all(
        item.get("agent_id") and item.get("task_id") and item.get("run_id")
        for item in artifacts
        if item.get("artifact_kind") in required_kinds
    )
    keys = (
        "target_agents_present",
        "message_done",
        "p1_rich_artifacts_file_blocks_present",
        "p1_rich_artifacts_manifest_present",
        "p1_rich_artifacts_block_manifest_aligned",
        "p1_rich_artifacts_manifest_has_task_run_agent",
    )
    report["acceptance"] = {key: bool(checks.get(key, False)) for key in keys}
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def _attempts_from_run_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict) or event.get("event_type") != "task_result":
            continue
        payload = event.get("payload")
        raw_attempts = payload.get("attempts") if isinstance(payload, dict) else None
        if isinstance(raw_attempts, list):
            attempts.extend(item for item in raw_attempts if isinstance(item, dict))
    return attempts


def evaluate_p1_evaluation_repair(report: dict[str, Any]) -> None:
    run_detail = report.get("orchestrator_run_detail")
    attempts = run_detail.get("attempts") if isinstance(run_detail, dict) else []
    events = run_detail.get("events") if isinstance(run_detail, dict) else []
    attempts = attempts if isinstance(attempts, list) else []
    events = events if isinstance(events, list) else []
    all_attempts = [*attempts, *_attempts_from_run_events(events)]
    artifacts = _artifacts(report)
    failed_attempts = [
        attempt
        for attempt in all_attempts
        if isinstance(attempt, dict)
        and any(
            isinstance(result, dict)
            and result.get("status") == "failed"
            and result.get("passed") is False
            for result in attempt.get("evaluation_results") or []
        )
    ]
    final_good_attempts = [
        attempt
        for attempt in all_attempts
        if isinstance(attempt, dict)
        and (attempt.get("final_state") or attempt.get("state"))
        in {"succeeded", "manual_review_required"}
    ]
    good_task_results = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("event_type") == "task_result"
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("final_state") in {"succeeded", "manual_review_required"}
    ]
    manifest_false_passed = [
        item
        for item in artifacts
        if item.get("evaluation_status") == "passed"
        and any(
            isinstance(result, dict)
            and (
                result.get("status") == "failed"
                or result.get("evaluator") == "manual_review_required"
            )
            for result in item.get("evaluation_results") or []
        )
    ]
    checks = report.setdefault("checks", {})
    checks["p1_evaluation_failed_seen"] = bool(failed_attempts)
    checks["p1_evaluation_reflection_seen"] = any(
        event.get("event_type") == "reflection_created" for event in events
    )
    checks["p1_evaluation_repair_or_fallback_seen"] = len(all_attempts) >= 2 or any(
        event.get("event_type") in {"agent_review_repair_scheduled", "repair_dispatched"}
        for event in events
    )
    checks["p1_evaluation_final_passed_or_manual"] = bool(
        final_good_attempts or good_task_results
    )
    checks["p1_evaluation_manifest_not_false_passed"] = not manifest_false_passed
    checks["p1_evaluation_manifest_status_present"] = any(
        item.get("evaluation_status") in {"failed", "passed", "manual_review_required"}
        for item in artifacts
    )
    report["evaluation_repair"] = {
        "failed_attempts": failed_attempts,
        "final_good_attempts": final_good_attempts,
        "good_task_results": good_task_results,
        "manifest_false_passed": manifest_false_passed,
    }
    keys = (
        "target_agents_present",
        "message_done",
        "p1_evaluation_failed_seen",
        "p1_evaluation_reflection_seen",
        "p1_evaluation_repair_or_fallback_seen",
        "p1_evaluation_final_passed_or_manual",
        "p1_evaluation_manifest_not_false_passed",
        "p1_evaluation_manifest_status_present",
    )
    report["acceptance"] = {key: bool(checks.get(key, False)) for key in keys}
    report["acceptance"]["passed"] = all(report["acceptance"].values())


def evaluate_p1_agent_capability_profile(report: dict[str, Any]) -> None:
    legacy.evaluate_p1_agent_capability_profile(report)


def evaluate_p2_agent_capability_profile_v2(report: dict[str, Any]) -> None:
    legacy.evaluate_p2_agent_capability_profile_v2(report)


def preserve_existing_acceptance(report: dict[str, Any]) -> None:
    acceptance = report.get("acceptance")
    if isinstance(acceptance, dict):
        acceptance["passed"] = all(
            bool(value) for key, value in acceptance.items() if key != "passed"
        )

