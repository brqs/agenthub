from scripts.orchestrator_live_e2e import (
    DEFAULT_P1_AGENT_CAPABILITY_PROFILE_REPORT_PATH,
    DEFAULT_P1_AGENT_CAPABILITY_PROFILE_SSE_PATH,
    DEFAULT_P1_EVALUATION_REPAIR_REPORT_PATH,
    DEFAULT_P1_EVALUATION_REPAIR_SSE_PATH,
    DEFAULT_P1_RICH_ARTIFACTS_REPORT_PATH,
    DEFAULT_P1_RICH_ARTIFACTS_SSE_PATH,
    DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_REPORT_PATH,
    DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_SSE_PATH,
    P1_AGENT_CAPABILITY_PROFILE_AGENT_IDS,
    P1_AGENT_CAPABILITY_PROFILE_PROMPT,
    P1_AGENT_CAPABILITY_PROFILE_SEED_PROMPT,
    P1_RICH_ARTIFACTS_PROMPT,
    P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT,
    SERVER_COMMAND_RE,
    evaluate_p1_agent_capability_profile,
    evaluate_p1_evaluation_repair,
    evaluate_p1_rich_artifacts,
    evaluate_p2_agent_capability_profile_v2,
)


def test_server_command_scan_ignores_negated_server_js_filename() -> None:
    assert SERVER_COMMAND_RE.search("No server.js or package.json was created.") is None


def test_server_command_scan_rejects_executable_server_js_command() -> None:
    assert SERVER_COMMAND_RE.search("Run node server.js to serve the app.") is not None


class FakeClient:
    def __init__(self, artifacts: list[dict[str, object]]) -> None:
        self.artifacts = artifacts

    def get(self, path: str, headers: dict[str, str]):
        assert path.endswith("/artifacts")
        assert headers == {"Authorization": "Bearer token"}
        return FakeResponse({"items": self.artifacts})


class FakeResponse:
    def __init__(self, body: dict[str, object]) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, object]:
        return self.body


def test_p1_rich_artifacts_defaults_are_registered() -> None:
    assert DEFAULT_P1_RICH_ARTIFACTS_REPORT_PATH == (
        "/tmp/agenthub_p1_rich_artifacts_report.json"
    )
    assert DEFAULT_P1_RICH_ARTIFACTS_SSE_PATH == (
        "/tmp/agenthub_p1_rich_artifacts_sse.jsonl"
    )
    assert DEFAULT_P1_EVALUATION_REPAIR_REPORT_PATH == (
        "/tmp/agenthub_p1_evaluation_repair_report.json"
    )
    assert DEFAULT_P1_EVALUATION_REPAIR_SSE_PATH == (
        "/tmp/agenthub_p1_evaluation_repair_sse.jsonl"
    )
    assert DEFAULT_P1_AGENT_CAPABILITY_PROFILE_REPORT_PATH == (
        "/tmp/agenthub_p1_agent_capability_profile_report.json"
    )
    assert DEFAULT_P1_AGENT_CAPABILITY_PROFILE_SSE_PATH == (
        "/tmp/agenthub_p1_agent_capability_profile_sse.jsonl"
    )
    assert DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_REPORT_PATH == (
        "/tmp/agenthub_p2_agent_capability_profile_v2_report.json"
    )
    assert DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_SSE_PATH == (
        "/tmp/agenthub_p2_agent_capability_profile_v2_sse.jsonl"
    )


def test_p1_rich_artifacts_archive_task_uses_shell_capable_agent() -> None:
    assert "任务四：opencode-helper 创建 packages/rich-export.tar" in (
        P1_RICH_ARTIFACTS_PROMPT
    )
    assert "tar -cf packages/rich-export.tar" in P1_RICH_ARTIFACTS_PROMPT
    assert "tar -tf packages/rich-export.tar" in P1_RICH_ARTIFACTS_PROMPT


def test_p1_agent_capability_profile_scenario_has_strong_seed_difference() -> None:
    assert P1_AGENT_CAPABILITY_PROFILE_AGENT_IDS == [
        "orchestrator",
        "claude-code",
        "opencode-helper",
    ]
    assert "claude-code" in P1_AGENT_CAPABILITY_PROFILE_SEED_PROMPT
    assert "evaluation_failed" in P1_AGENT_CAPABILITY_PROFILE_SEED_PROMPT
    assert "整个 seed run 必须只有一个 task" in P1_AGENT_CAPABILITY_PROFILE_SEED_PROMPT
    assert "禁止为 repair 另建任务" in P1_AGENT_CAPABILITY_PROFILE_SEED_PROMPT
    assert "不得继续解释、再次 Write、自行评估、自行修复或模拟 fallback" in (
        P1_AGENT_CAPABILITY_PROFILE_SEED_PROMPT
    )
    assert "只能由 Orchestrator runtime" in P1_AGENT_CAPABILITY_PROFILE_SEED_PROMPT
    assert "具体执行 Agent" in P1_AGENT_CAPABILITY_PROFILE_PROMPT
    assert "只规划一个逻辑文档任务" in P1_AGENT_CAPABILITY_PROFILE_PROMPT
    assert "所有实际 attempt" in P1_AGENT_CAPABILITY_PROFILE_PROMPT


def test_p2_agent_capability_profile_v2_prompt_uses_user_scope_without_agent_name() -> None:
    assert "Agent capability profile v2 from recent user Orchestrator runs" in (
        P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT
    )
    assert "User preference memory from recent Orchestrator runs" in (
        P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT
    )
    assert "p2-capability-v2-followup.md" in P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT
    assert "不点名任何执行 Agent" in P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT
    assert "claude-code" not in P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT
    assert "opencode-helper" not in P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT
    assert "codex-helper" not in P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT


def test_evaluate_p1_agent_capability_profile_checks_actual_selected_agent() -> None:
    report = _agent_capability_profile_report(
        task_agent="opencode-helper",
        attempt_agent="opencode-helper",
    )

    evaluate_p1_agent_capability_profile(report)

    assert report["acceptance"]["p1_agent_capability_seed_claude_failed"] is True
    assert report["acceptance"]["p1_agent_capability_seed_opencode_succeeded"] is True
    assert (
        report["acceptance"]["p1_agent_capability_followup_task_agent_opencode"] is True
    )
    assert (
        report["acceptance"]["p1_agent_capability_followup_attempt_agent_opencode"] is True
    )
    assert report["acceptance"]["passed"] is True


def test_evaluate_p1_agent_capability_profile_rejects_summary_only_claim() -> None:
    report = _agent_capability_profile_report(
        task_agent="claude-code",
        attempt_agent="claude-code",
    )

    evaluate_p1_agent_capability_profile(report)

    assert (
        report["acceptance"]["p1_agent_capability_followup_task_agent_opencode"]
        is False
    )
    assert (
        report["acceptance"]["p1_agent_capability_followup_attempt_agent_opencode"]
        is False
    )
    assert report["acceptance"]["passed"] is False


def test_evaluate_p2_agent_capability_profile_v2_checks_cross_conversation_selection() -> None:
    report = _agent_capability_profile_v2_report(
        task_agent="opencode-helper",
        attempt_agent="opencode-helper",
    )

    evaluate_p2_agent_capability_profile_v2(report)

    assert report["acceptance"]["p2_agent_capability_v2_api_user_scope"] is True
    assert (
        report["acceptance"][
            "p2_agent_capability_v2_new_conversation_empty_before_followup"
        ]
        is True
    )
    assert report["acceptance"]["p2_agent_capability_v2_seed_claude_failed"] is True
    assert report["acceptance"]["p2_agent_capability_v2_seed_opencode_succeeded"] is True
    assert (
        report["acceptance"]["p2_agent_capability_v2_followup_task_agent_opencode"]
        is True
    )
    assert (
        report["acceptance"]["p2_agent_capability_v2_followup_attempt_agent_opencode"]
        is True
    )
    assert report["acceptance"]["passed"] is True


def test_evaluate_p2_agent_capability_profile_v2_rejects_wrong_actual_agent() -> None:
    report = _agent_capability_profile_v2_report(
        task_agent="claude-code",
        attempt_agent="claude-code",
    )

    evaluate_p2_agent_capability_profile_v2(report)

    assert (
        report["acceptance"]["p2_agent_capability_v2_followup_task_agent_opencode"]
        is False
    )
    assert (
        report["acceptance"]["p2_agent_capability_v2_followup_attempt_agent_opencode"]
        is False
    )
    assert report["acceptance"]["passed"] is False


def _agent_capability_profile_report(
    *,
    task_agent: str,
    attempt_agent: str,
) -> dict[str, object]:
    return {
        "agent_capability_profile_before_followup": {
            "items": [
                {
                    "agent_id": "claude-code",
                    "task_count": 1,
                    "success_count": 0,
                    "failure_count": 1,
                    "evaluation_failed_count": 1,
                },
                {
                    "agent_id": "opencode-helper",
                    "task_count": 1,
                    "success_count": 1,
                    "failure_count": 0,
                    "evaluation_failed_count": 0,
                },
            ]
        },
        "agent_capability_profile": {
            "items": [
                {"agent_id": "claude-code"},
                {"agent_id": "opencode-helper"},
            ]
        },
        "orchestrator_runs": [
            {
                "final_summary": (
                    "Agent capability profile from recent Orchestrator runs; "
                    "recent success 选择依据: opencode-helper"
                )
            }
        ],
        "orchestrator_run_detail": {
            "tasks": [
                {
                    "task_id": "followup",
                    "agent_id": task_agent,
                    "title": "Create capability-followup.md",
                    "instruction": "Create capability-followup.md",
                    "expected_output": "capability-followup.md",
                }
            ],
            "attempts": [
                {
                    "task_id": "followup",
                    "agent_id": attempt_agent,
                    "state": "succeeded",
                }
            ],
        },
        "target_agent_message": {"content": []},
        "workspace_files": [{"path": "capability-followup.md"}],
    }


def _agent_capability_profile_v2_report(
    *,
    task_agent: str,
    attempt_agent: str,
) -> dict[str, object]:
    return {
        "followup_runs_before_count": 0,
        "agent_capability_profile_v2_before_followup": {
            "scope": "user",
            "source_conversation_count": 1,
            "runs_considered": 1,
            "preferences": {"artifact_preferences": {"document": 2}},
            "items": [
                {
                    "agent_id": "claude-code",
                    "task_count": 1,
                    "success_count": 0,
                    "failure_count": 1,
                    "evaluation_failed_count": 1,
                    "score": -1.5,
                },
                {
                    "agent_id": "opencode-helper",
                    "task_count": 1,
                    "success_count": 1,
                    "failure_count": 0,
                    "evaluation_failed_count": 0,
                    "score": 2.0,
                },
            ],
        },
        "orchestrator_runs": [
            {
                "final_summary": (
                    "Agent capability profile v2 from recent user Orchestrator runs; "
                    "User preference memory from recent Orchestrator runs; "
                    "user-scope recent success 选择依据: opencode-helper"
                )
            }
        ],
        "orchestrator_run_detail": {
            "tasks": [
                {
                    "task_id": "followup-v2",
                    "agent_id": task_agent,
                    "title": "Create p2-capability-v2-followup.md",
                    "instruction": "Create p2-capability-v2-followup.md",
                    "expected_output": "p2-capability-v2-followup.md",
                }
            ],
            "attempts": [
                {
                    "task_id": "followup-v2",
                    "agent_id": attempt_agent,
                    "state": "succeeded",
                }
            ],
        },
        "target_agent_message": {"content": []},
        "workspace_files": [{"path": "p2-capability-v2-followup.md"}],
    }


def test_evaluate_p1_rich_artifacts_acceptance_uses_artifacts_api() -> None:
    artifacts = [
        {
            "path": "docs/report.md",
            "artifact_kind": "document",
            "agent_id": "codex-helper",
            "task_id": "task-doc",
            "run_id": "run-1",
        },
        {
            "path": "slides/deck.pptx",
            "artifact_kind": "ppt",
            "agent_id": "claude-code",
            "task_id": "task-ppt",
            "run_id": "run-1",
        },
        {
            "path": "assets/logo.svg",
            "artifact_kind": "image",
            "agent_id": "opencode-helper",
            "task_id": "task-image",
            "run_id": "run-1",
        },
        {
            "path": "packages/export.zip",
            "artifact_kind": "archive",
            "agent_id": "codex-helper",
            "task_id": "task-archive",
            "run_id": "run-1",
        },
    ]
    report = {
        "conversation_id": "conversation-1",
        "checks": {"target_agents_present": True, "message_done": True},
        "target_agent_message": {
            "content": [
                {"type": "file", **artifact}
                for artifact in artifacts
            ]
        },
    }

    evaluate_p1_rich_artifacts(
        FakeClient(artifacts),
        {"Authorization": "Bearer token"},
        report,
    )

    assert report["acceptance"]["passed"] is True
    assert report["acceptance"]["p1_rich_artifacts_block_manifest_aligned"] is True


def test_evaluate_p1_evaluation_repair_rejects_false_passed_manifest() -> None:
    report = {
        "conversation_id": "conversation-1",
        "checks": {"target_agents_present": True, "message_done": True},
        "orchestrator_run_detail": {
            "attempts": [
                {
                    "state": "evaluation_failed",
                    "evaluation_results": [
                        {
                            "status": "failed",
                            "passed": False,
                            "checked_artifacts": ["report.md"],
                        }
                    ],
                },
                {"state": "succeeded", "evaluation_results": []},
            ],
            "events": [{"event_type": "reflection_created"}],
        },
    }
    artifacts = [
        {
            "path": "report.md",
            "evaluation_status": "passed",
            "evaluation_results": [
                {
                    "evaluator": "document_quality",
                    "status": "failed",
                    "passed": False,
                    "checked_artifacts": ["report.md"],
                }
            ],
        }
    ]

    evaluate_p1_evaluation_repair(
        FakeClient(artifacts),
        {"Authorization": "Bearer token"},
        report,
    )

    assert report["acceptance"]["p1_evaluation_manifest_not_false_passed"] is False
    assert report["acceptance"]["passed"] is False


def test_evaluate_p1_evaluation_repair_reads_event_attempts() -> None:
    report = {
        "conversation_id": "conversation-1",
        "checks": {"target_agents_present": True, "message_done": True},
        "orchestrator_run_detail": {
            "attempts": [
                {
                    "state": "evaluation_failed",
                    "evaluation_results": None,
                }
            ],
            "events": [
                {"event_type": "reflection_created"},
                {
                    "event_type": "task_result",
                    "payload": {
                        "final_state": "succeeded",
                        "attempts": [
                            {
                                "state": "evaluation_failed",
                                "evaluation_results": [
                                    {
                                        "status": "failed",
                                        "passed": False,
                                        "checked_artifacts": ["report.md"],
                                    }
                                ],
                            },
                            {
                                "state": "succeeded",
                                "evaluation_results": [
                                    {
                                        "status": "passed",
                                        "passed": True,
                                        "checked_artifacts": ["report.md"],
                                    }
                                ],
                            },
                        ],
                    },
                },
            ],
        },
    }
    artifacts = [
        {
            "path": "report.md",
            "evaluation_status": "passed",
            "evaluation_results": [
                {
                    "evaluator": "document_quality",
                    "status": "passed",
                    "passed": True,
                    "checked_artifacts": ["report.md"],
                }
            ],
        }
    ]

    evaluate_p1_evaluation_repair(
        FakeClient(artifacts),
        {"Authorization": "Bearer token"},
        report,
    )

    assert report["acceptance"]["p1_evaluation_failed_seen"] is True
    assert report["acceptance"]["p1_evaluation_final_passed_or_manual"] is True
    assert report["acceptance"]["passed"] is True
