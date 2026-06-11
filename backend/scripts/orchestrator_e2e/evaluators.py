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


def _checks(report: dict[str, Any]) -> dict[str, Any]:
    checks = report.setdefault("checks", {})
    return checks if isinstance(checks, dict) else {}


def _run_detail(report: dict[str, Any]) -> dict[str, Any]:
    detail = report.get("orchestrator_run_detail")
    return detail if isinstance(detail, dict) else {}


def _workspace_paths(report: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for item in report.get("workspace_files") or []:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            paths.add(str(item["path"]).rsplit("/", 1)[-1])
    for item in _artifacts(report):
        if isinstance(item.get("path"), str):
            paths.add(str(item["path"]).rsplit("/", 1)[-1])
    return paths


def evaluate_parallel_dag(report: dict[str, Any]) -> None:
    parallel = legacy.fullstack_parallel_report(_run_detail(report))
    report["parallel_tasks"] = parallel
    _checks(report)["parallel_dag_passed"] = parallel.get("passed") is True


def evaluate_group_members_only(
    report: dict[str, Any],
    *,
    allowed_agent_ids: set[str] | None = None,
) -> None:
    allowed = allowed_agent_ids or {
        "orchestrator",
        "claude-code",
        "opencode-helper",
        "codex-helper",
    }
    switched = [
        item
        for item in report.get("agent_switch_to_agents") or []
        if isinstance(item, str)
    ]
    child_agents = [
        item.get("agent_id")
        for item in report.get("child_agent_messages") or []
        if isinstance(item, dict) and isinstance(item.get("agent_id"), str)
    ]
    invalid = sorted(
        {agent_id for agent_id in [*switched, *child_agents] if agent_id not in allowed}
    )
    report["group_member_scope"] = {
        "allowed_agent_ids": sorted(allowed),
        "invalid_agent_ids": invalid,
    }
    _checks(report)["group_dispatch_only_allowed_members"] = not invalid


def evaluate_task_card_agent_attribution(report: dict[str, Any]) -> None:
    tasks: list[dict[str, Any]] = []
    for block in _content_blocks(report):
        if block.get("type") != "task_card":
            continue
        raw_tasks = block.get("tasks")
        if isinstance(raw_tasks, list):
            tasks.extend(item for item in raw_tasks if isinstance(item, dict))
    mismatches = [
        task
        for task in tasks
        if task.get("final_agent_id")
        and task.get("agent_id")
        and task.get("agent_id") != task.get("final_agent_id")
    ]
    fallback_tasks = [
        task
        for task in tasks
        if task.get("planned_agent_id")
        and task.get("final_agent_id")
        and task.get("planned_agent_id") != task.get("final_agent_id")
    ]
    report["task_card_agent_attribution"] = {
        "task_count": len(tasks),
        "fallback_task_count": len(fallback_tasks),
        "mismatches": mismatches,
    }
    checks = _checks(report)
    checks["task_card_agent_attribution_present"] = bool(tasks)
    checks["task_card_agent_matches_final_agent"] = not mismatches


def evaluate_workspace_artifacts(
    report: dict[str, Any],
    *,
    required_files: set[str],
) -> None:
    paths = _workspace_paths(report)
    missing = sorted(required_files - paths)
    report["workspace_artifact_check"] = {
        "required_files": sorted(required_files),
        "missing_files": missing,
    }
    _checks(report)["workspace_required_artifacts_present"] = not missing


def evaluate_browser_repair_loop(report: dict[str, Any]) -> None:
    browser = report.get("browser_verification")
    browser = browser if isinstance(browser, dict) else report.get("browser_report")
    browser = browser if isinstance(browser, dict) else {}
    repair_trace = report.get("repair_trace")
    repair_trace = repair_trace if isinstance(repair_trace, dict) else {}
    checks = _checks(report)
    checks["browser_verify_passed"] = browser.get("passed") is True or bool(
        checks.get("browser_verify_passed")
    )
    checks["browser_repair_trace_present_if_needed"] = bool(
        checks.get("browser_repaired_if_needed")
        or repair_trace.get("has_repair_or_fallback")
        or checks["browser_verify_passed"]
    )


def evaluate_context_continuity(report: dict[str, Any]) -> None:
    followups = report.get("context_followups")
    followups = followups if isinstance(followups, list) else []
    checks = _checks(report)
    checks["context_followups_present"] = bool(followups)
    checks["context_followups_all_passed"] = bool(followups) and all(
        item.get("passed") is True for item in followups if isinstance(item, dict)
    )


def evaluate_sensitive_trace_absent(report: dict[str, Any]) -> None:
    text = "\n".join(
        str(value)
        for value in (
            report.get("sse_message_error_text"),
            report.get("dialogue_visible_forbidden_terms"),
            report.get("presentation_visible_forbidden_terms"),
        )
        if value
    )
    forbidden = legacy.forbidden_visible_terms(text)
    report["sensitive_trace_check"] = {"forbidden_terms": forbidden}
    _checks(report)["visible_text_no_sensitive_trace"] = not forbidden


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
