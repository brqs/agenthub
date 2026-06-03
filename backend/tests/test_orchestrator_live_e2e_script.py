from scripts.orchestrator_live_e2e import (
    DEFAULT_P1_EVALUATION_REPAIR_REPORT_PATH,
    DEFAULT_P1_EVALUATION_REPAIR_SSE_PATH,
    DEFAULT_P1_RICH_ARTIFACTS_REPORT_PATH,
    DEFAULT_P1_RICH_ARTIFACTS_SSE_PATH,
    P1_RICH_ARTIFACTS_PROMPT,
    SERVER_COMMAND_RE,
    evaluate_p1_evaluation_repair,
    evaluate_p1_rich_artifacts,
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


def test_p1_rich_artifacts_archive_task_uses_shell_capable_agent() -> None:
    assert "任务四：opencode-helper 创建 packages/rich-export.tar" in (
        P1_RICH_ARTIFACTS_PROMPT
    )
    assert "tar -cf packages/rich-export.tar" in P1_RICH_ARTIFACTS_PROMPT
    assert "tar -tf packages/rich-export.tar" in P1_RICH_ARTIFACTS_PROMPT


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
