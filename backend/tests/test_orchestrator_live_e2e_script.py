import pytest

from app.agents.orchestrator.availability import scoped_runnable_agent_ids
from scripts.orchestrator_e2e.config import SCENARIO_DEFAULTS, load_settings
from scripts.orchestrator_e2e.evaluators import (
    evaluate_browser_repair_loop,
    evaluate_context_continuity,
    evaluate_group_members_only,
    evaluate_parallel_dag,
    evaluate_sensitive_trace_absent,
    evaluate_task_card_agent_attribution,
    evaluate_workspace_artifacts,
)
from scripts.orchestrator_e2e.runner import (
    AGENT_FALLBACK_E2E_FAIL_RUNTIME,
    AGENT_FALLBACK_E2E_WRITE_RUNTIME,
    AGENT_FALLBACK_MATRIX_CASES,
    BUILTIN_SUB_AGENT_IDS,
    _child_output_contract,
    _looks_generic_completion,
    _unresolved_missing_artifact_paths,
    command_fulfillment_statuses,
    evaluate_fallback_task_card_case,
    fallback_group_agent_ids,
    forbidden_visible_terms,
    message_error_text,
)
from scripts.orchestrator_e2e.scenarios import SCENARIOS
from scripts.orchestrator_live_e2e import (
    AGENT_FALLBACK_MATRIX_PROMPT,
    COMMAND_FULFILLMENT_PROMPT,
    CUSTOM_AGENT_READER_REVIEW_REPAIR_PROMPT,
    CYBERPUNK_QUALITY_PROMPT,
    CYBERPUNK_QUALITY_V2_PROMPT,
    DEFAULT_AGENT_FALLBACK_MATRIX_REPORT_PATH,
    DEFAULT_AGENT_FALLBACK_MATRIX_SSE_PATH,
    DEFAULT_COMMAND_FULFILLMENT_REPORT_PATH,
    DEFAULT_COMMAND_FULFILLMENT_SSE_PATH,
    DEFAULT_CONTEXT_FOLLOWUP_REPORT_PATH,
    DEFAULT_CONTEXT_FOLLOWUP_SSE_PATH,
    DEFAULT_CUSTOM_AGENT_READER_REVIEW_REPAIR_REPORT_PATH,
    DEFAULT_CUSTOM_AGENT_READER_REVIEW_REPAIR_SSE_PATH,
    DEFAULT_CYBERPUNK_QUALITY_REPORT_PATH,
    DEFAULT_CYBERPUNK_QUALITY_SSE_PATH,
    DEFAULT_CYBERPUNK_QUALITY_V2_REPORT_PATH,
    DEFAULT_CYBERPUNK_QUALITY_V2_SSE_PATH,
    DEFAULT_GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_REPORT_PATH,
    DEFAULT_GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_SSE_PATH,
    DEFAULT_GROUP_DIALOGUE_DEBATE_REPORT_PATH,
    DEFAULT_GROUP_DIALOGUE_DEBATE_SSE_PATH,
    DEFAULT_GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_REPORT_PATH,
    DEFAULT_GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_SSE_PATH,
    DEFAULT_GROUP_SUBSTANTIVE_OUTPUT_MATRIX_REPORT_PATH,
    DEFAULT_GROUP_SUBSTANTIVE_OUTPUT_MATRIX_SSE_PATH,
    DEFAULT_IM_CONTEXT_PIN_FOLLOWUP_REPAIR_REPORT_PATH,
    DEFAULT_IM_CONTEXT_PIN_FOLLOWUP_REPAIR_SSE_PATH,
    DEFAULT_IM_DIALOGUE_NO_ARTIFACT_TURN_TAKING_V2_REPORT_PATH,
    DEFAULT_IM_DIALOGUE_NO_ARTIFACT_TURN_TAKING_V2_SSE_PATH,
    DEFAULT_P1_AGENT_CAPABILITY_PROFILE_REPORT_PATH,
    DEFAULT_P1_AGENT_CAPABILITY_PROFILE_SSE_PATH,
    DEFAULT_P1_EVALUATION_REPAIR_REPORT_PATH,
    DEFAULT_P1_EVALUATION_REPAIR_SSE_PATH,
    DEFAULT_P1_RICH_ARTIFACTS_REPORT_PATH,
    DEFAULT_P1_RICH_ARTIFACTS_SSE_PATH,
    DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_REPORT_PATH,
    DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_SSE_PATH,
    DEFAULT_PRESENTATION_MARKERS_REPORT_PATH,
    DEFAULT_PRESENTATION_MARKERS_SSE_PATH,
    DEFAULT_STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_REPORT_PATH,
    DEFAULT_STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_SSE_PATH,
    DEFAULT_TASK_MANAGER_PARALLEL_REPORT_PATH,
    DEFAULT_TASK_MANAGER_PARALLEL_SSE_PATH,
    DEFAULT_TASK_MANAGER_PARALLEL_V2_REPORT_PATH,
    DEFAULT_TASK_MANAGER_PARALLEL_V2_SSE_PATH,
    GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_PROMPT,
    GROUP_DIALOGUE_DEBATE_PROMPT,
    GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_PROMPT,
    GROUP_PROCESS_DATA_ANALYSIS_PROMPT,
    GROUP_PROCESS_DOCUMENT_STRATEGY_PROMPT,
    GROUP_PROCESS_FAILURE_READABLE_PROMPT,
    GROUP_PROCESS_WORKFLOW_DELIVERY_PROMPT,
    GROUP_SUBSTANTIVE_OUTPUT_MATRIX_PROMPT,
    IM_CONTEXT_PIN_FOLLOWUP_REPAIR_PROMPT,
    P1_AGENT_CAPABILITY_PROFILE_AGENT_IDS,
    P1_AGENT_CAPABILITY_PROFILE_PROMPT,
    P1_AGENT_CAPABILITY_PROFILE_SEED_PROMPT,
    P1_RICH_ARTIFACTS_PROMPT,
    P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT,
    PRESENTATION_COLLAPSE_PROMPT,
    SERVER_COMMAND_RE,
    STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_PROMPT,
    TASK_MANAGER_PARALLEL_PROMPT,
    TASK_MANAGER_PARALLEL_V2_PROMPT,
    evaluate_p1_agent_capability_profile,
    evaluate_p1_evaluation_repair,
    evaluate_p1_rich_artifacts,
    evaluate_p2_agent_capability_profile_v2,
)


def test_server_command_scan_ignores_negated_server_js_filename() -> None:
    assert SERVER_COMMAND_RE.search("No server.js or package.json was created.") is None


def test_server_command_scan_rejects_executable_server_js_command() -> None:
    assert SERVER_COMMAND_RE.search("Run node server.js to serve the app.") is not None


def test_child_output_contract_accepts_concise_artifact_summary() -> None:
    message = {
        "id": "msg-1",
        "agent_id": "opencode-helper",
        "status": "done",
        "content": [
            {
                "type": "text",
                "presentation": {"role": "agent_summary"},
                "text": (
                    "已完成：创建任务卡片静态前端组件。\n"
                    "产物：index.html、styles.css、app.js。\n"
                    "验证：2/2 项通过。"
                ),
            }
        ],
    }

    contract = _child_output_contract(message)

    assert contract["substantive_output_passed"] is True
    assert contract["terminal_output_accepted"] is True
    assert contract["failure_reason"] == ""


def test_unresolved_missing_artifact_paths_ignores_recovered_fallback_files() -> None:
    run_detail = {
        "attempts": [
            {
                "task_id": "auto-1",
                "agent_id": "claude-code",
                "missing_artifact_paths": ["index.html", "styles.css", "app.js"],
                "artifact_paths": [],
                "error": "missing artifact: index.html, styles.css, app.js",
            },
            {
                "task_id": "auto-1",
                "agent_id": "opencode-helper",
                "missing_artifact_paths": [],
                "artifact_paths": ["index.html", "styles.css", "app.js"],
                "error": None,
            },
        ]
    }

    assert _unresolved_missing_artifact_paths(run_detail) == []


def test_unresolved_missing_artifact_paths_ignores_later_task_recovery() -> None:
    run_detail = {
        "attempts": [
            {
                "task_id": "auto-1",
                "missing_artifact_paths": ["index.html", "styles.css", "app.js"],
                "artifact_paths": [],
            },
            {
                "task_id": "auto-2",
                "missing_artifact_paths": [],
                "artifact_paths": ["index.html", "styles.css", "app.js"],
                "error": "non-fatal review issue after files were written",
            },
        ]
    }

    assert _unresolved_missing_artifact_paths(run_detail) == []


def test_unresolved_missing_artifact_paths_keeps_unrecovered_files() -> None:
    run_detail = {
        "attempts": [
            {
                "task_id": "auto-1",
                "missing_artifact_paths": ["index.html", "styles.css", "app.js"],
                "artifact_paths": [],
            },
            {
                "task_id": "auto-1",
                "missing_artifact_paths": [],
                "artifact_paths": ["index.html", "styles.css"],
            },
        ]
    }

    assert _unresolved_missing_artifact_paths(run_detail) == ["app.js"]


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


def test_scenario_registry_covers_all_existing_names_and_defaults() -> None:
    assert set(SCENARIOS) == set(SCENARIO_DEFAULTS)
    for name, spec in SCENARIOS.items():
        defaults = SCENARIO_DEFAULTS[name]
        assert str(spec.default_report_path) == defaults.report_path
        assert str(spec.default_sse_path) == defaults.sse_path
        assert str(spec.default_browser_report_path) == defaults.browser_report_path


def test_all_scenario_report_and_sse_defaults_match_legacy_paths() -> None:
    expected = {
        "quality": (
            "/tmp/agenthub_orchestrator_quality_report.json",
            "/tmp/agenthub_orchestrator_quality_sse.jsonl",
        ),
        "fullstack": (
            "/tmp/agenthub_fullstack_flow_report.json",
            "/tmp/agenthub_fullstack_flow_sse.jsonl",
        ),
        "fullstack_task_manager_parallel_repair": (
            "/tmp/agenthub_task_manager_parallel_report.json",
            "/tmp/agenthub_task_manager_parallel_sse.jsonl",
        ),
        "fullstack_task_manager_parallel_repair_v2": (
            "/tmp/agenthub_task_manager_parallel_v2_report.json",
            "/tmp/agenthub_task_manager_parallel_v2_sse.jsonl",
        ),
        "cyberpunk_site_quality_repair_8082": (
            "/tmp/agenthub_cyberpunk_quality_report.json",
            "/tmp/agenthub_cyberpunk_quality_sse.jsonl",
        ),
        "cyberpunk_site_quality_repair_8082_v2": (
            "/tmp/agenthub_cyberpunk_quality_v2_report.json",
            "/tmp/agenthub_cyberpunk_quality_v2_sse.jsonl",
        ),
        "im_context_pin_followup_repair": (
            "/tmp/agenthub_im_context_pin_followup_repair_report.json",
            "/tmp/agenthub_im_context_pin_followup_repair_sse.jsonl",
        ),
        "group_chat_attribution_process_matrix": (
            "/tmp/agenthub_group_chat_attribution_process_matrix_report.json",
            "/tmp/agenthub_group_chat_attribution_process_matrix_sse.jsonl",
        ),
        "custom_agent_reader_review_repair": (
            "/tmp/agenthub_custom_agent_reader_review_repair_report.json",
            "/tmp/agenthub_custom_agent_reader_review_repair_sse.jsonl",
        ),
        "static_package_deploy_repair_matrix": (
            "/tmp/agenthub_static_package_deploy_repair_matrix_report.json",
            "/tmp/agenthub_static_package_deploy_repair_matrix_sse.jsonl",
        ),
        "group_member_fallback_repair_visibility": (
            "/tmp/agenthub_group_member_fallback_repair_visibility_report.json",
            "/tmp/agenthub_group_member_fallback_repair_visibility_sse.jsonl",
        ),
        "im_dialogue_no_artifact_turn_taking_v2": (
            "/tmp/agenthub_im_dialogue_no_artifact_turn_taking_v2_report.json",
            "/tmp/agenthub_im_dialogue_no_artifact_turn_taking_v2_sse.jsonl",
        ),
        "deployment": (
            "/tmp/agenthub_deployment_flow_report.json",
            "/tmp/agenthub_deployment_flow_sse.jsonl",
        ),
        "deployment_repair": (
            "/tmp/agenthub_deployment_repair_flow_report.json",
            "/tmp/agenthub_deployment_repair_flow_sse.jsonl",
        ),
        "custom_agent_tools": (
            "/tmp/agenthub_custom_agent_tools_report.json",
            "/tmp/agenthub_custom_agent_tools_sse.jsonl",
        ),
        "architected_frontend_group_chat_repair": (
            "/tmp/agenthub_architected_frontend_group_chat_report.json",
            "/tmp/agenthub_architected_frontend_group_chat_sse.jsonl",
        ),
        "group_process_document_strategy": (
            "/tmp/agenthub_group_process_document_strategy_report.json",
            "/tmp/agenthub_group_process_document_strategy_sse.jsonl",
        ),
        "group_process_data_analysis": (
            "/tmp/agenthub_group_process_data_analysis_report.json",
            "/tmp/agenthub_group_process_data_analysis_sse.jsonl",
        ),
        "group_process_workflow_delivery": (
            "/tmp/agenthub_group_process_workflow_delivery_report.json",
            "/tmp/agenthub_group_process_workflow_delivery_sse.jsonl",
        ),
        "group_process_failure_readable": (
            "/tmp/agenthub_group_process_failure_readable_report.json",
            "/tmp/agenthub_group_process_failure_readable_sse.jsonl",
        ),
        "group_process_frontend_preview": (
            "/tmp/agenthub_group_process_frontend_preview_report.json",
            "/tmp/agenthub_group_process_frontend_preview_sse.jsonl",
        ),
        "agent_fallback_matrix": (
            "/tmp/agenthub_agent_fallback_matrix_report.json",
            "/tmp/agenthub_agent_fallback_matrix_sse.jsonl",
        ),
        "command_fulfillment_cyberpunk_group_deploy": (
            "/tmp/agenthub_command_fulfillment_report.json",
            "/tmp/agenthub_command_fulfillment_sse.jsonl",
        ),
        "orchestrator_context_followup_repair": (
            "/tmp/agenthub_orchestrator_context_followup_report.json",
            "/tmp/agenthub_orchestrator_context_followup_sse.jsonl",
        ),
        "presentation_collapse_markers_smoke": (
            "/tmp/agenthub_presentation_markers_report.json",
            "/tmp/agenthub_presentation_markers_sse.jsonl",
        ),
        "group_dialogue_debate_no_artifacts": (
            "/tmp/agenthub_group_dialogue_debate_report.json",
            "/tmp/agenthub_group_dialogue_debate_sse.jsonl",
        ),
        "group_substantive_output_matrix": (
            "/tmp/agenthub_group_substantive_output_matrix_report.json",
            "/tmp/agenthub_group_substantive_output_matrix_sse.jsonl",
        ),
        "agent_turn_taking_dialogue_repair": (
            "/tmp/agenthub_agent_turn_taking_dialogue_report.json",
            "/tmp/agenthub_agent_turn_taking_dialogue_sse.jsonl",
        ),
        "agent_turn_taking_matrix": (
            "/tmp/agenthub_agent_turn_taking_matrix_report.json",
            "/tmp/agenthub_agent_turn_taking_matrix_sse.jsonl",
        ),
        "manual_two_agent_turn_taking": (
            "/tmp/agenthub_manual_two_agent_turn_taking_report.json",
            "/tmp/agenthub_manual_two_agent_turn_taking_sse.jsonl",
        ),
        "p1_attribution": (
            "/tmp/agenthub_p1_attribution_report.json",
            "/tmp/agenthub_p1_attribution_sse.jsonl",
        ),
        "p1_workflow": (
            "/tmp/agenthub_p1_workflow_report.json",
            "/tmp/agenthub_p1_workflow_sse.jsonl",
        ),
        "p1_workflow_runtime": (
            "/tmp/agenthub_p1_workflow_runtime_report.json",
            "/tmp/agenthub_p1_workflow_runtime_sse.jsonl",
        ),
        "p1_review_thread_repair": (
            "/tmp/agenthub_p1_review_thread_report.json",
            "/tmp/agenthub_p1_review_thread_sse.jsonl",
        ),
        "p1_rich_artifacts": (
            "/tmp/agenthub_p1_rich_artifacts_report.json",
            "/tmp/agenthub_p1_rich_artifacts_sse.jsonl",
        ),
        "p1_evaluation_repair": (
            "/tmp/agenthub_p1_evaluation_repair_report.json",
            "/tmp/agenthub_p1_evaluation_repair_sse.jsonl",
        ),
        "p1_agent_capability_profile": (
            "/tmp/agenthub_p1_agent_capability_profile_report.json",
            "/tmp/agenthub_p1_agent_capability_profile_sse.jsonl",
        ),
        "p2_agent_capability_profile_v2": (
            "/tmp/agenthub_p2_agent_capability_profile_v2_report.json",
            "/tmp/agenthub_p2_agent_capability_profile_v2_sse.jsonl",
        ),
        "one_click_container_deploy_repair_loop": (
            "/tmp/agenthub_one_click_container_deploy_repair_report.json",
            "/tmp/agenthub_one_click_container_deploy_repair_sse.jsonl",
        ),
    }

    assert {
        name: (defaults.report_path, defaults.sse_path)
        for name, defaults in SCENARIO_DEFAULTS.items()
    } == expected


def test_presentation_marker_scenario_defaults_are_registered() -> None:
    assert DEFAULT_PRESENTATION_MARKERS_REPORT_PATH == (
        "/tmp/agenthub_presentation_markers_report.json"
    )
    assert DEFAULT_PRESENTATION_MARKERS_SSE_PATH == (
        "/tmp/agenthub_presentation_markers_sse.jsonl"
    )
    assert "presentation marker" in PRESENTATION_COLLAPSE_PROMPT.lower()


def test_task_manager_parallel_scenario_defaults_and_prompt_are_registered() -> None:
    assert DEFAULT_TASK_MANAGER_PARALLEL_REPORT_PATH == (
        "/tmp/agenthub_task_manager_parallel_report.json"
    )
    assert DEFAULT_TASK_MANAGER_PARALLEL_SSE_PATH == (
        "/tmp/agenthub_task_manager_parallel_sse.jsonl"
    )
    assert "任务管理 Demo" in TASK_MANAGER_PARALLEL_PROMPT
    assert "两个智能体并行开发" in TASK_MANAGER_PARALLEL_PROMPT
    assert "backend_app.py" in TASK_MANAGER_PARALLEL_PROMPT
    assert "review.md" in TASK_MANAGER_PARALLEL_PROMPT
    spec = SCENARIOS["fullstack_task_manager_parallel_repair"]
    assert spec.prompt == TASK_MANAGER_PARALLEL_PROMPT
    assert str(spec.default_report_path) == DEFAULT_TASK_MANAGER_PARALLEL_REPORT_PATH
    assert str(spec.default_sse_path) == DEFAULT_TASK_MANAGER_PARALLEL_SSE_PATH


def test_cyberpunk_quality_scenario_defaults_and_prompt_are_registered() -> None:
    assert DEFAULT_CYBERPUNK_QUALITY_REPORT_PATH == (
        "/tmp/agenthub_cyberpunk_quality_report.json"
    )
    assert DEFAULT_CYBERPUNK_QUALITY_SSE_PATH == (
        "/tmp/agenthub_cyberpunk_quality_sse.jsonl"
    )
    assert "赛博朋克" in CYBERPUNK_QUALITY_PROMPT
    assert "部署在端口8082" in CYBERPUNK_QUALITY_PROMPT
    assert "浏览器级质量验收" in CYBERPUNK_QUALITY_PROMPT
    spec = SCENARIOS["cyberpunk_site_quality_repair_8082"]
    assert spec.prompt == CYBERPUNK_QUALITY_PROMPT
    assert str(spec.default_report_path) == DEFAULT_CYBERPUNK_QUALITY_REPORT_PATH
    assert str(spec.default_sse_path) == DEFAULT_CYBERPUNK_QUALITY_SSE_PATH


def test_robustness_repair_loop_scenarios_are_registered() -> None:
    turn_taking_prompt = SCENARIOS["agent_turn_taking_dialogue_repair"].prompt
    expected = {
        "fullstack_task_manager_parallel_repair_v2": (
            DEFAULT_TASK_MANAGER_PARALLEL_V2_REPORT_PATH,
            DEFAULT_TASK_MANAGER_PARALLEL_V2_SSE_PATH,
            TASK_MANAGER_PARALLEL_V2_PROMPT,
            "repair loop",
        ),
        "cyberpunk_site_quality_repair_8082_v2": (
            DEFAULT_CYBERPUNK_QUALITY_V2_REPORT_PATH,
            DEFAULT_CYBERPUNK_QUALITY_V2_SSE_PATH,
            CYBERPUNK_QUALITY_V2_PROMPT,
            "端口8082",
        ),
        "im_context_pin_followup_repair": (
            DEFAULT_IM_CONTEXT_PIN_FOLLOWUP_REPAIR_REPORT_PATH,
            DEFAULT_IM_CONTEXT_PIN_FOLLOWUP_REPAIR_SSE_PATH,
            IM_CONTEXT_PIN_FOLLOWUP_REPAIR_PROMPT,
            "Planner 大上下文",
        ),
        "group_chat_attribution_process_matrix": (
            DEFAULT_GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_REPORT_PATH,
            DEFAULT_GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_SSE_PATH,
            GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_PROMPT,
            "不得调用群聊外 Agent",
        ),
        "custom_agent_reader_review_repair": (
            DEFAULT_CUSTOM_AGENT_READER_REVIEW_REPAIR_REPORT_PATH,
            DEFAULT_CUSTOM_AGENT_READER_REVIEW_REPAIR_SSE_PATH,
            CUSTOM_AGENT_READER_REVIEW_REPAIR_PROMPT,
            "read_file",
        ),
        "static_package_deploy_repair_matrix": (
            DEFAULT_STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_REPORT_PATH,
            DEFAULT_STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_SSE_PATH,
            STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_PROMPT,
            "源码包必须排除密钥",
        ),
        "group_member_fallback_repair_visibility": (
            DEFAULT_GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_REPORT_PATH,
            DEFAULT_GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_SSE_PATH,
            GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_PROMPT,
            "planned agent",
        ),
        "im_dialogue_no_artifact_turn_taking_v2": (
            DEFAULT_IM_DIALOGUE_NO_ARTIFACT_TURN_TAKING_V2_REPORT_PATH,
            DEFAULT_IM_DIALOGUE_NO_ARTIFACT_TURN_TAKING_V2_SSE_PATH,
            turn_taking_prompt,
            "不需要生成文件",
        ),
    }

    for name, (report_path, sse_path, prompt, marker) in expected.items():
        spec = SCENARIOS[name]
        assert str(spec.default_report_path) == report_path
        assert str(spec.default_sse_path) == sse_path
        assert spec.prompt == prompt
        assert marker in prompt
        assert "writer" not in prompt
        assert "web-designer" not in prompt


def test_group_dialogue_debate_scenario_defaults_are_registered() -> None:
    assert DEFAULT_GROUP_DIALOGUE_DEBATE_REPORT_PATH == (
        "/tmp/agenthub_group_dialogue_debate_report.json"
    )
    assert DEFAULT_GROUP_DIALOGUE_DEBATE_SSE_PATH == (
        "/tmp/agenthub_group_dialogue_debate_sse.jsonl"
    )
    assert "不需要生成文件" in GROUP_DIALOGUE_DEBATE_PROMPT
    assert "辩论" in GROUP_DIALOGUE_DEBATE_PROMPT


def test_group_substantive_output_matrix_scenario_defaults_are_registered() -> None:
    assert DEFAULT_GROUP_SUBSTANTIVE_OUTPUT_MATRIX_REPORT_PATH == (
        "/tmp/agenthub_group_substantive_output_matrix_report.json"
    )
    assert DEFAULT_GROUP_SUBSTANTIVE_OUTPUT_MATRIX_SSE_PATH == (
        "/tmp/agenthub_group_substantive_output_matrix_sse.jsonl"
    )
    assert "实质输出" in GROUP_SUBSTANTIVE_OUTPUT_MATRIX_PROMPT
    assert "不需要生成文件" in GROUP_SUBSTANTIVE_OUTPUT_MATRIX_PROMPT


def test_load_settings_honors_artifact_path_overrides() -> None:
    settings = load_settings(
        {
            "AGENTHUB_E2E_REPORT_PATH": "/tmp/custom-report.json",
            "AGENTHUB_E2E_SSE_PATH": "/tmp/custom-sse.jsonl",
            "AGENTHUB_E2E_BROWSER_REPORT_PATH": "/tmp/custom-browser.json",
        }
    )

    assert str(settings.report_path) == "/tmp/custom-report.json"
    assert str(settings.sse_path) == "/tmp/custom-sse.jsonl"
    assert str(settings.browser_report_path) == "/tmp/custom-browser.json"


def test_load_settings_does_not_embed_real_credentials_by_default() -> None:
    settings = load_settings({})

    assert settings.username == ""
    assert settings.password == ""


def test_load_settings_uses_temporary_user_for_capability_v2_by_default() -> None:
    settings = load_settings(
        {"AGENTHUB_E2E_SCENARIO": "p2_agent_capability_profile_v2"}
    )

    assert settings.use_temporary_user is True


def test_load_settings_respects_explicit_capability_v2_username() -> None:
    settings = load_settings(
        {
            "AGENTHUB_E2E_SCENARIO": "p2_agent_capability_profile_v2",
            "AGENTHUB_E2E_USERNAME": "existing-user",
        }
    )

    assert settings.use_temporary_user is False


@pytest.mark.parametrize("status", ["not_supported", "published", "any"])
def test_load_settings_accepts_container_status_expectations(status: str) -> None:
    assert (
        load_settings({"AGENTHUB_E2E_EXPECT_CONTAINER_STATUS": status}).expect_container_status
        == status
    )


def test_load_settings_rejects_unknown_container_status_expectation() -> None:
    with pytest.raises(ValueError, match="must be not_supported, published, or any"):
        load_settings({"AGENTHUB_E2E_EXPECT_CONTAINER_STATUS": "queued"})


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


def test_group_process_scenarios_cover_distinct_non_template_tasks() -> None:
    assert "strategy-architecture.md" in GROUP_PROCESS_DOCUMENT_STRATEGY_PROMPT
    assert "sample-metrics.csv" in GROUP_PROCESS_DATA_ANALYSIS_PROMPT
    assert "group-process-workflow.yaml" in GROUP_PROCESS_WORKFLOW_DELIVERY_PROMPT
    assert "../outside-workspace.txt" in GROUP_PROCESS_FAILURE_READABLE_PROMPT
    combined = "\n".join(
        (
            GROUP_PROCESS_DOCUMENT_STRATEGY_PROMPT,
            GROUP_PROCESS_DATA_ANALYSIS_PROMPT,
            GROUP_PROCESS_WORKFLOW_DELIVERY_PROMPT,
            GROUP_PROCESS_FAILURE_READABLE_PROMPT,
        )
    )
    assert "前端开发演示" not in combined
    assert "index.html、styles.css、app.js" not in combined
    assert "codex-helper" not in combined
    assert "Claude Code" in combined
    assert "OpenCode Helper" in combined


def test_agent_fallback_matrix_defaults_and_prompt_are_generic() -> None:
    assert DEFAULT_AGENT_FALLBACK_MATRIX_REPORT_PATH == (
        "/tmp/agenthub_agent_fallback_matrix_report.json"
    )
    assert DEFAULT_AGENT_FALLBACK_MATRIX_SSE_PATH == (
        "/tmp/agenthub_agent_fallback_matrix_sse.jsonl"
    )
    assert "fallback" in AGENT_FALLBACK_MATRIX_PROMPT.lower()
    assert "markdown" in AGENT_FALLBACK_MATRIX_PROMPT
    assert "前端开发演示" not in AGENT_FALLBACK_MATRIX_PROMPT
    assert "8082" not in AGENT_FALLBACK_MATRIX_PROMPT
    assert set(BUILTIN_SUB_AGENT_IDS) == {
        "claude-code",
        "opencode-helper",
        "codex-helper",
    }
    for case in AGENT_FALLBACK_MATRIX_CASES:
        target_agent_id = str(case["target_agent_id"])
        group_agent_ids = fallback_group_agent_ids(target_agent_id)
        assert "writer" not in group_agent_ids
        assert "web-designer" not in group_agent_ids
        assert group_agent_ids == [
            "orchestrator",
            target_agent_id,
            *(agent_id for agent_id in BUILTIN_SUB_AGENT_IDS if agent_id != target_agent_id),
        ]
    claude_case = next(
        case
        for case in AGENT_FALLBACK_MATRIX_CASES
        if case["target_agent_id"] == "claude-code"
    )
    codex_case = next(
        case
        for case in AGENT_FALLBACK_MATRIX_CASES
        if case["target_agent_id"] == "codex-helper"
    )
    assert "agent_provider_patch" not in codex_case
    assert "agent_provider_patch" not in claude_case
    assert (
        codex_case["sub_agent_config_overrides"]["codex-helper"]["command"]
        == ["python3", AGENT_FALLBACK_E2E_FAIL_RUNTIME]
    )
    assert (
        claude_case["sub_agent_config_overrides"]["claude-code"]["command"]
        == ["python3", AGENT_FALLBACK_E2E_FAIL_RUNTIME]
    )
    assert claude_case["sub_agent_config_overrides"]["claude-code"]["runtime"] == "cli"
    assert (
        claude_case["sub_agent_config_overrides"]["opencode-helper"]["command"]
        == ["python3", AGENT_FALLBACK_E2E_WRITE_RUNTIME]
    )


def test_command_fulfillment_scenario_defaults_and_prompt_are_registered() -> None:
    assert DEFAULT_COMMAND_FULFILLMENT_REPORT_PATH == (
        "/tmp/agenthub_command_fulfillment_report.json"
    )
    assert DEFAULT_COMMAND_FULFILLMENT_SSE_PATH == (
        "/tmp/agenthub_command_fulfillment_sse.jsonl"
    )
    assert "赛博朋克" in COMMAND_FULFILLMENT_PROMPT
    assert "两个智能体" in COMMAND_FULFILLMENT_PROMPT
    assert "部署在端口8082" in COMMAND_FULFILLMENT_PROMPT
    assert "源码" not in COMMAND_FULFILLMENT_PROMPT
    spec = SCENARIOS["command_fulfillment_cyberpunk_group_deploy"]
    assert spec.prompt == COMMAND_FULFILLMENT_PROMPT
    assert str(spec.default_report_path) == DEFAULT_COMMAND_FULFILLMENT_REPORT_PATH
    assert str(spec.default_sse_path) == DEFAULT_COMMAND_FULFILLMENT_SSE_PATH


def test_context_followup_scenario_defaults_and_prompt_are_registered() -> None:
    assert DEFAULT_CONTEXT_FOLLOWUP_REPORT_PATH == (
        "/tmp/agenthub_orchestrator_context_followup_report.json"
    )
    assert DEFAULT_CONTEXT_FOLLOWUP_SSE_PATH == (
        "/tmp/agenthub_orchestrator_context_followup_sse.jsonl"
    )
    spec = SCENARIOS["orchestrator_context_followup_repair"]
    assert spec.prompt == COMMAND_FULFILLMENT_PROMPT
    assert str(spec.default_report_path) == DEFAULT_CONTEXT_FOLLOWUP_REPORT_PATH
    assert str(spec.default_sse_path) == DEFAULT_CONTEXT_FOLLOWUP_SSE_PATH


def test_command_fulfillment_statuses_preserve_satisfied_evidence() -> None:
    run_detail = {
        "events": [
            {
                "event_type": "command_fulfillment_status",
                "payload": {
                    "items": [
                        {"id": "deployment", "status": "satisfied"},
                        {"id": "browser_verify", "status": "satisfied"},
                    ]
                },
            },
            {
                "event_type": "command_fulfillment_status",
                "payload": {
                    "items": [
                        {"id": "deployment", "status": "pending"},
                        {"id": "browser_verify", "status": "failed"},
                    ]
                },
            },
        ]
    }

    assert command_fulfillment_statuses(run_detail) == {
        "deployment": "satisfied",
        "browser_verify": "satisfied",
    }


def test_message_error_text_scans_sse_error_payloads_for_raw_runtime_terms() -> None:
    events = [
        {
            "event": "message_error",
            "data": {
                "error": (
                    "OpenAI Codex v0.137.0 workdir: /workspaces/demo "
                    "approval: never (external_runtime_error)"
                )
            },
        }
    ]

    text = message_error_text(events)

    assert "OpenAI Codex" in text
    assert "external_runtime_error" in forbidden_visible_terms(text)


def test_available_agents_authoritative_false_allows_e2e_fallback_scope() -> None:
    config = {
        "available_agents_authoritative": False,
        "available_agents": [
            {"id": "codex-helper", "availability": {"status": "unavailable"}},
        ],
    }

    assert scoped_runnable_agent_ids(config) is None


def test_substantive_output_summary_accepts_file_level_artifact_summary() -> None:
    assert not _looks_generic_completion(
        "已完成：Produce solution。\n产物：index.html、styles.css、app.js。\n验证：2/2 项通过。"
    )
    assert _looks_generic_completion("已完成：Produce solution。")


def test_evaluate_fallback_task_card_case_accepts_actual_fallback_agent() -> None:
    report = _fallback_task_card_report(
        planned_agent="claude-code",
        task_agent="opencode-helper",
        final_agent="opencode-helper",
        attempt_agents=["claude-code", "opencode-helper"],
    )

    result = evaluate_fallback_task_card_case(report)

    assert result["passed"] is True
    assert result["planned_agent_matches_target"] is True
    assert result["task_agent_matches_final_attempt"] is True
    assert result["final_agent_matches_final_attempt"] is True
    assert result["task_agent_reassigned_from_planned"] is True


def test_evaluate_fallback_task_card_case_rejects_original_agent_display() -> None:
    report = _fallback_task_card_report(
        planned_agent="claude-code",
        task_agent="claude-code",
        final_agent="claude-code",
        attempt_agents=["claude-code", "opencode-helper"],
    )

    result = evaluate_fallback_task_card_case(report)

    assert result["passed"] is False
    assert result["task_agent_matches_final_attempt"] is False
    assert result["task_agent_reassigned_from_planned"] is False


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


def _fallback_task_card_report(
    *,
    planned_agent: str,
    task_agent: str,
    final_agent: str,
    attempt_agents: list[str],
) -> dict[str, object]:
    return {
        "target_agent_id": planned_agent,
        "target_agent_message": {
            "content": [
                {
                    "type": "task_card",
                    "tasks": [
                        {
                            "id": "fallback-task",
                            "agent_id": task_agent,
                            "planned_agent_id": planned_agent,
                            "final_agent_id": final_agent,
                            "title": "Create fallback evidence",
                            "status": "done",
                        }
                    ],
                }
            ],
        },
        "orchestrator_run_detail": {
            "attempts": [
                {
                    "task_id": "fallback-task",
                    "agent_id": agent_id,
                    "state": "failed" if agent_id == planned_agent else "succeeded",
                }
                for agent_id in attempt_agents
            ],
        },
    }


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
        "workspace_artifacts_api": artifacts,
        "target_agent_message": {
            "content": [
                {"type": "file", **artifact}
                for artifact in artifacts
            ]
        },
    }

    evaluate_p1_rich_artifacts(report)

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
    report["workspace_artifacts_api"] = [
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

    evaluate_p1_evaluation_repair(report)

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
    report["workspace_artifacts_api"] = [
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

    evaluate_p1_evaluation_repair(report)

    assert report["acceptance"]["p1_evaluation_failed_seen"] is True
    assert report["acceptance"]["p1_evaluation_final_passed_or_manual"] is True
    assert report["acceptance"]["passed"] is True


def test_shared_robustness_evaluators_accept_good_report() -> None:
    report = {
        "checks": {
            "browser_repaired_if_needed": True,
        },
        "agent_switch_to_agents": ["claude-code", "opencode-helper"],
        "child_agent_messages": [
            {"agent_id": "claude-code"},
            {"agent_id": "opencode-helper"},
        ],
        "workspace_files": [
            {"path": "index.html"},
            {"path": "styles.css"},
            {"path": "app.js"},
            {"path": "review.md"},
        ],
        "browser_verification": {"passed": True},
        "context_followups": [{"passed": True}, {"passed": True}],
        "orchestrator_run_detail": {
            "tasks": [
                {"task_id": "frontend_impl", "depends_on": []},
                {"task_id": "backend_impl", "depends_on": []},
                {
                    "task_id": "review",
                    "depends_on": ["frontend_impl", "backend_impl"],
                },
            ],
            "events": [
                {"event_type": "task_started", "task_id": "frontend_impl"},
                {"event_type": "task_started", "task_id": "backend_impl"},
                {"event_type": "task_result", "task_id": "frontend_impl"},
                {"event_type": "task_result", "task_id": "backend_impl"},
                {"event_type": "task_started", "task_id": "review"},
            ],
        },
        "target_agent_message": {
            "content": [
                {
                    "type": "task_card",
                    "tasks": [
                        {
                            "id": "frontend_impl",
                            "agent_id": "claude-code",
                            "planned_agent_id": "claude-code",
                            "final_agent_id": "claude-code",
                        }
                    ],
                }
            ]
        },
    }

    evaluate_parallel_dag(report)
    evaluate_group_members_only(report)
    evaluate_task_card_agent_attribution(report)
    evaluate_workspace_artifacts(
        report,
        required_files={"index.html", "styles.css", "app.js", "review.md"},
    )
    evaluate_browser_repair_loop(report)
    evaluate_context_continuity(report)
    evaluate_sensitive_trace_absent(report)

    checks = report["checks"]
    assert checks["parallel_dag_passed"] is True
    assert checks["group_dispatch_only_allowed_members"] is True
    assert checks["task_card_agent_matches_final_agent"] is True
    assert checks["workspace_required_artifacts_present"] is True
    assert checks["browser_verify_passed"] is True
    assert checks["context_followups_all_passed"] is True
    assert checks["visible_text_no_sensitive_trace"] is True


def test_shared_robustness_evaluators_reject_bad_report() -> None:
    report = {
        "checks": {},
        "agent_switch_to_agents": ["claude-code", "writer"],
        "child_agent_messages": [{"agent_id": "web-designer"}],
        "workspace_files": [{"path": "index.html"}],
        "sse_message_error_text": "OpenAI Codex external_runtime_error",
        "target_agent_message": {
            "content": [
                {
                    "type": "task_card",
                    "tasks": [
                        {
                            "id": "fallback-task",
                            "agent_id": "claude-code",
                            "planned_agent_id": "claude-code",
                            "final_agent_id": "opencode-helper",
                        }
                    ],
                }
            ]
        },
    }

    evaluate_group_members_only(report)
    evaluate_task_card_agent_attribution(report)
    evaluate_workspace_artifacts(
        report,
        required_files={"index.html", "styles.css", "app.js"},
    )
    evaluate_sensitive_trace_absent(report)

    checks = report["checks"]
    assert checks["group_dispatch_only_allowed_members"] is False
    assert checks["task_card_agent_matches_final_agent"] is False
    assert checks["workspace_required_artifacts_present"] is False
    assert checks["visible_text_no_sensitive_trace"] is False
