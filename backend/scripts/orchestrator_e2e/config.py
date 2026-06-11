"""Environment-backed settings and stable artifact path defaults."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "http://154.44.25.94:1573"
DEFAULT_USERNAME = ""
DEFAULT_PASSWORD = ""
DEFAULT_SCENARIO = "quality"
CONTAINER_STATUS_EXPECTATIONS = frozenset({"not_supported", "published", "any"})

DEFAULT_P1_ATTRIBUTION_SSE_PATH = "/tmp/agenthub_p1_attribution_sse.jsonl"  # noqa: S108
DEFAULT_P1_WORKFLOW_SSE_PATH = "/tmp/agenthub_p1_workflow_sse.jsonl"  # noqa: S108
DEFAULT_P1_WORKFLOW_RUNTIME_SSE_PATH = "/tmp/agenthub_p1_workflow_runtime_sse.jsonl"  # noqa: S108
DEFAULT_P1_REVIEW_THREAD_SSE_PATH = "/tmp/agenthub_p1_review_thread_sse.jsonl"  # noqa: S108
DEFAULT_P1_RICH_ARTIFACTS_SSE_PATH = "/tmp/agenthub_p1_rich_artifacts_sse.jsonl"  # noqa: S108
DEFAULT_P1_EVALUATION_REPAIR_SSE_PATH = "/tmp/agenthub_p1_evaluation_repair_sse.jsonl"  # noqa: S108
DEFAULT_P1_AGENT_CAPABILITY_PROFILE_SSE_PATH = "/tmp/agenthub_p1_agent_capability_profile_sse.jsonl"  # noqa: S108
DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_p2_agent_capability_profile_v2_sse.jsonl"  # noqa: S108
)
DEFAULT_FULLSTACK_SSE_PATH = "/tmp/agenthub_fullstack_flow_sse.jsonl"  # noqa: S108
DEFAULT_TASK_MANAGER_PARALLEL_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_task_manager_parallel_sse.jsonl"  # noqa: S108
)
DEFAULT_TASK_MANAGER_PARALLEL_V2_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_task_manager_parallel_v2_sse.jsonl"  # noqa: S108
)
DEFAULT_QUALITY_SSE_PATH = "/tmp/agenthub_orchestrator_quality_sse.jsonl"  # noqa: S108
DEFAULT_CYBERPUNK_QUALITY_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_cyberpunk_quality_sse.jsonl"  # noqa: S108
)
DEFAULT_CYBERPUNK_QUALITY_V2_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_cyberpunk_quality_v2_sse.jsonl"  # noqa: S108
)
DEFAULT_IM_CONTEXT_PIN_FOLLOWUP_REPAIR_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_im_context_pin_followup_repair_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_chat_attribution_process_matrix_sse.jsonl"  # noqa: S108
)
DEFAULT_CUSTOM_AGENT_READER_REVIEW_REPAIR_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_custom_agent_reader_review_repair_sse.jsonl"  # noqa: S108
)
DEFAULT_STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_static_package_deploy_repair_matrix_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_member_fallback_repair_visibility_sse.jsonl"  # noqa: S108
)
DEFAULT_IM_DIALOGUE_NO_ARTIFACT_TURN_TAKING_V2_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_im_dialogue_no_artifact_turn_taking_v2_sse.jsonl"  # noqa: S108
)
DEFAULT_DEPLOYMENT_SSE_PATH = "/tmp/agenthub_deployment_flow_sse.jsonl"  # noqa: S108
DEFAULT_DEPLOYMENT_REPAIR_SSE_PATH = "/tmp/agenthub_deployment_repair_flow_sse.jsonl"  # noqa: S108
DEFAULT_ONE_CLICK_CONTAINER_DEPLOY_REPAIR_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_one_click_container_deploy_repair_sse.jsonl"  # noqa: S108
)
DEFAULT_CUSTOM_AGENT_TOOLS_SSE_PATH = "/tmp/agenthub_custom_agent_tools_sse.jsonl"  # noqa: S108
DEFAULT_ARCHITECTED_FRONTEND_GROUP_CHAT_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_architected_frontend_group_chat_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_DOCUMENT_STRATEGY_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_document_strategy_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_DATA_ANALYSIS_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_data_analysis_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_WORKFLOW_DELIVERY_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_workflow_delivery_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_FAILURE_READABLE_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_failure_readable_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_FRONTEND_PREVIEW_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_frontend_preview_sse.jsonl"  # noqa: S108
)
DEFAULT_AGENT_FALLBACK_MATRIX_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_agent_fallback_matrix_sse.jsonl"  # noqa: S108
)
DEFAULT_COMMAND_FULFILLMENT_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_command_fulfillment_sse.jsonl"  # noqa: S108
)
DEFAULT_CONTEXT_FOLLOWUP_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_orchestrator_context_followup_sse.jsonl"  # noqa: S108
)
DEFAULT_PRESENTATION_MARKERS_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_presentation_markers_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_DIALOGUE_DEBATE_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_dialogue_debate_sse.jsonl"  # noqa: S108
)
DEFAULT_GROUP_SUBSTANTIVE_OUTPUT_MATRIX_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_group_substantive_output_matrix_sse.jsonl"  # noqa: S108
)
DEFAULT_AGENT_TURN_TAKING_DIALOGUE_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_agent_turn_taking_dialogue_sse.jsonl"  # noqa: S108
)
DEFAULT_AGENT_TURN_TAKING_MATRIX_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_agent_turn_taking_matrix_sse.jsonl"  # noqa: S108
)
DEFAULT_MANUAL_TWO_AGENT_TURN_TAKING_SSE_PATH = (  # noqa: S108
    "/tmp/agenthub_manual_two_agent_turn_taking_sse.jsonl"  # noqa: S108
)

DEFAULT_P1_ATTRIBUTION_REPORT_PATH = "/tmp/agenthub_p1_attribution_report.json"  # noqa: S108
DEFAULT_P1_WORKFLOW_REPORT_PATH = "/tmp/agenthub_p1_workflow_report.json"  # noqa: S108
DEFAULT_P1_WORKFLOW_RUNTIME_REPORT_PATH = "/tmp/agenthub_p1_workflow_runtime_report.json"  # noqa: S108
DEFAULT_P1_REVIEW_THREAD_REPORT_PATH = "/tmp/agenthub_p1_review_thread_report.json"  # noqa: S108
DEFAULT_P1_RICH_ARTIFACTS_REPORT_PATH = "/tmp/agenthub_p1_rich_artifacts_report.json"  # noqa: S108
DEFAULT_P1_EVALUATION_REPAIR_REPORT_PATH = "/tmp/agenthub_p1_evaluation_repair_report.json"  # noqa: S108
DEFAULT_P1_AGENT_CAPABILITY_PROFILE_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_p1_agent_capability_profile_report.json"  # noqa: S108
)
DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_p2_agent_capability_profile_v2_report.json"  # noqa: S108
)
DEFAULT_FULLSTACK_REPORT_PATH = "/tmp/agenthub_fullstack_flow_report.json"  # noqa: S108
DEFAULT_TASK_MANAGER_PARALLEL_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_task_manager_parallel_report.json"  # noqa: S108
)
DEFAULT_TASK_MANAGER_PARALLEL_V2_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_task_manager_parallel_v2_report.json"  # noqa: S108
)
DEFAULT_QUALITY_REPORT_PATH = "/tmp/agenthub_orchestrator_quality_report.json"  # noqa: S108
DEFAULT_CYBERPUNK_QUALITY_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_cyberpunk_quality_report.json"  # noqa: S108
)
DEFAULT_CYBERPUNK_QUALITY_V2_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_cyberpunk_quality_v2_report.json"  # noqa: S108
)
DEFAULT_IM_CONTEXT_PIN_FOLLOWUP_REPAIR_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_im_context_pin_followup_repair_report.json"  # noqa: S108
)
DEFAULT_GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_chat_attribution_process_matrix_report.json"  # noqa: S108
)
DEFAULT_CUSTOM_AGENT_READER_REVIEW_REPAIR_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_custom_agent_reader_review_repair_report.json"  # noqa: S108
)
DEFAULT_STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_static_package_deploy_repair_matrix_report.json"  # noqa: S108
)
DEFAULT_GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_member_fallback_repair_visibility_report.json"  # noqa: S108
)
DEFAULT_IM_DIALOGUE_NO_ARTIFACT_TURN_TAKING_V2_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_im_dialogue_no_artifact_turn_taking_v2_report.json"  # noqa: S108
)
DEFAULT_DEPLOYMENT_REPORT_PATH = "/tmp/agenthub_deployment_flow_report.json"  # noqa: S108
DEFAULT_DEPLOYMENT_REPAIR_REPORT_PATH = "/tmp/agenthub_deployment_repair_flow_report.json"  # noqa: S108
DEFAULT_ONE_CLICK_CONTAINER_DEPLOY_REPAIR_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_one_click_container_deploy_repair_report.json"  # noqa: S108
)
DEFAULT_CUSTOM_AGENT_TOOLS_REPORT_PATH = "/tmp/agenthub_custom_agent_tools_report.json"  # noqa: S108
DEFAULT_ARCHITECTED_FRONTEND_GROUP_CHAT_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_architected_frontend_group_chat_report.json"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_DOCUMENT_STRATEGY_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_document_strategy_report.json"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_DATA_ANALYSIS_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_data_analysis_report.json"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_WORKFLOW_DELIVERY_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_workflow_delivery_report.json"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_FAILURE_READABLE_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_failure_readable_report.json"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_FRONTEND_PREVIEW_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_frontend_preview_report.json"  # noqa: S108
)
DEFAULT_AGENT_FALLBACK_MATRIX_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_agent_fallback_matrix_report.json"  # noqa: S108
)
DEFAULT_COMMAND_FULFILLMENT_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_command_fulfillment_report.json"  # noqa: S108
)
DEFAULT_CONTEXT_FOLLOWUP_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_orchestrator_context_followup_report.json"  # noqa: S108
)
DEFAULT_PRESENTATION_MARKERS_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_presentation_markers_report.json"  # noqa: S108
)
DEFAULT_GROUP_DIALOGUE_DEBATE_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_dialogue_debate_report.json"  # noqa: S108
)
DEFAULT_GROUP_SUBSTANTIVE_OUTPUT_MATRIX_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_substantive_output_matrix_report.json"  # noqa: S108
)
DEFAULT_AGENT_TURN_TAKING_DIALOGUE_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_agent_turn_taking_dialogue_report.json"  # noqa: S108
)
DEFAULT_AGENT_TURN_TAKING_MATRIX_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_agent_turn_taking_matrix_report.json"  # noqa: S108
)
DEFAULT_MANUAL_TWO_AGENT_TURN_TAKING_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_manual_two_agent_turn_taking_report.json"  # noqa: S108
)

DEFAULT_FULLSTACK_BROWSER_REPORT_PATH = "/tmp/agenthub_fullstack_flow_browser.json"  # noqa: S108
DEFAULT_TASK_MANAGER_PARALLEL_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_task_manager_parallel_browser.json"  # noqa: S108
)
DEFAULT_TASK_MANAGER_PARALLEL_V2_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_task_manager_parallel_v2_browser.json"  # noqa: S108
)
DEFAULT_QUALITY_BROWSER_REPORT_PATH = "/tmp/agenthub_orchestrator_quality_browser.json"  # noqa: S108
DEFAULT_CYBERPUNK_QUALITY_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_cyberpunk_quality_browser.json"  # noqa: S108
)
DEFAULT_CYBERPUNK_QUALITY_V2_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_cyberpunk_quality_v2_browser.json"  # noqa: S108
)
DEFAULT_IM_CONTEXT_PIN_FOLLOWUP_REPAIR_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_im_context_pin_followup_repair_browser.json"  # noqa: S108
)
DEFAULT_GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_chat_attribution_process_matrix_browser.json"  # noqa: S108
)
DEFAULT_CUSTOM_AGENT_READER_REVIEW_REPAIR_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_custom_agent_reader_review_repair_browser.json"  # noqa: S108
)
DEFAULT_STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_static_package_deploy_repair_matrix_browser.json"  # noqa: S108
)
DEFAULT_GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_member_fallback_repair_visibility_browser.json"  # noqa: S108
)
DEFAULT_IM_DIALOGUE_NO_ARTIFACT_TURN_TAKING_V2_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_im_dialogue_no_artifact_turn_taking_v2_browser.json"  # noqa: S108
)
DEFAULT_DEPLOYMENT_BROWSER_REPORT_PATH = "/tmp/agenthub_deployment_flow_browser.json"  # noqa: S108
DEFAULT_DEPLOYMENT_REPAIR_BROWSER_REPORT_PATH = "/tmp/agenthub_deployment_repair_flow_browser.json"  # noqa: S108
DEFAULT_ARCHITECTED_FRONTEND_GROUP_CHAT_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_architected_frontend_group_chat_browser.json"  # noqa: S108
)
DEFAULT_GROUP_PROCESS_FRONTEND_PREVIEW_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_group_process_frontend_preview_browser.json"  # noqa: S108
)
DEFAULT_COMMAND_FULFILLMENT_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_command_fulfillment_browser.json"  # noqa: S108
)
DEFAULT_CONTEXT_FOLLOWUP_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_orchestrator_context_followup_browser.json"  # noqa: S108
)
DEFAULT_PRESENTATION_MARKERS_BROWSER_REPORT_PATH = (  # noqa: S108
    "/tmp/agenthub_presentation_markers_browser.json"  # noqa: S108
)


@dataclass(frozen=True)
class ScenarioDefaults:
    report_path: str
    sse_path: str
    browser_report_path: str = DEFAULT_QUALITY_BROWSER_REPORT_PATH


SCENARIO_DEFAULTS: dict[str, ScenarioDefaults] = {
    "quality": ScenarioDefaults(DEFAULT_QUALITY_REPORT_PATH, DEFAULT_QUALITY_SSE_PATH),
    "fullstack": ScenarioDefaults(
        DEFAULT_FULLSTACK_REPORT_PATH,
        DEFAULT_FULLSTACK_SSE_PATH,
        DEFAULT_FULLSTACK_BROWSER_REPORT_PATH,
    ),
    "fullstack_task_manager_parallel_repair": ScenarioDefaults(
        DEFAULT_TASK_MANAGER_PARALLEL_REPORT_PATH,
        DEFAULT_TASK_MANAGER_PARALLEL_SSE_PATH,
        DEFAULT_TASK_MANAGER_PARALLEL_BROWSER_REPORT_PATH,
    ),
    "fullstack_task_manager_parallel_repair_v2": ScenarioDefaults(
        DEFAULT_TASK_MANAGER_PARALLEL_V2_REPORT_PATH,
        DEFAULT_TASK_MANAGER_PARALLEL_V2_SSE_PATH,
        DEFAULT_TASK_MANAGER_PARALLEL_V2_BROWSER_REPORT_PATH,
    ),
    "cyberpunk_site_quality_repair_8082": ScenarioDefaults(
        DEFAULT_CYBERPUNK_QUALITY_REPORT_PATH,
        DEFAULT_CYBERPUNK_QUALITY_SSE_PATH,
        DEFAULT_CYBERPUNK_QUALITY_BROWSER_REPORT_PATH,
    ),
    "cyberpunk_site_quality_repair_8082_v2": ScenarioDefaults(
        DEFAULT_CYBERPUNK_QUALITY_V2_REPORT_PATH,
        DEFAULT_CYBERPUNK_QUALITY_V2_SSE_PATH,
        DEFAULT_CYBERPUNK_QUALITY_V2_BROWSER_REPORT_PATH,
    ),
    "im_context_pin_followup_repair": ScenarioDefaults(
        DEFAULT_IM_CONTEXT_PIN_FOLLOWUP_REPAIR_REPORT_PATH,
        DEFAULT_IM_CONTEXT_PIN_FOLLOWUP_REPAIR_SSE_PATH,
        DEFAULT_IM_CONTEXT_PIN_FOLLOWUP_REPAIR_BROWSER_REPORT_PATH,
    ),
    "group_chat_attribution_process_matrix": ScenarioDefaults(
        DEFAULT_GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_REPORT_PATH,
        DEFAULT_GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_SSE_PATH,
        DEFAULT_GROUP_CHAT_ATTRIBUTION_PROCESS_MATRIX_BROWSER_REPORT_PATH,
    ),
    "custom_agent_reader_review_repair": ScenarioDefaults(
        DEFAULT_CUSTOM_AGENT_READER_REVIEW_REPAIR_REPORT_PATH,
        DEFAULT_CUSTOM_AGENT_READER_REVIEW_REPAIR_SSE_PATH,
        DEFAULT_CUSTOM_AGENT_READER_REVIEW_REPAIR_BROWSER_REPORT_PATH,
    ),
    "static_package_deploy_repair_matrix": ScenarioDefaults(
        DEFAULT_STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_REPORT_PATH,
        DEFAULT_STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_SSE_PATH,
        DEFAULT_STATIC_PACKAGE_DEPLOY_REPAIR_MATRIX_BROWSER_REPORT_PATH,
    ),
    "group_member_fallback_repair_visibility": ScenarioDefaults(
        DEFAULT_GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_REPORT_PATH,
        DEFAULT_GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_SSE_PATH,
        DEFAULT_GROUP_MEMBER_FALLBACK_REPAIR_VISIBILITY_BROWSER_REPORT_PATH,
    ),
    "im_dialogue_no_artifact_turn_taking_v2": ScenarioDefaults(
        DEFAULT_IM_DIALOGUE_NO_ARTIFACT_TURN_TAKING_V2_REPORT_PATH,
        DEFAULT_IM_DIALOGUE_NO_ARTIFACT_TURN_TAKING_V2_SSE_PATH,
        DEFAULT_IM_DIALOGUE_NO_ARTIFACT_TURN_TAKING_V2_BROWSER_REPORT_PATH,
    ),
    "deployment": ScenarioDefaults(
        DEFAULT_DEPLOYMENT_REPORT_PATH,
        DEFAULT_DEPLOYMENT_SSE_PATH,
        DEFAULT_DEPLOYMENT_BROWSER_REPORT_PATH,
    ),
    "deployment_repair": ScenarioDefaults(
        DEFAULT_DEPLOYMENT_REPAIR_REPORT_PATH,
        DEFAULT_DEPLOYMENT_REPAIR_SSE_PATH,
        DEFAULT_DEPLOYMENT_REPAIR_BROWSER_REPORT_PATH,
    ),
    "one_click_container_deploy_repair_loop": ScenarioDefaults(
        DEFAULT_ONE_CLICK_CONTAINER_DEPLOY_REPAIR_REPORT_PATH,
        DEFAULT_ONE_CLICK_CONTAINER_DEPLOY_REPAIR_SSE_PATH,
        DEFAULT_DEPLOYMENT_REPAIR_BROWSER_REPORT_PATH,
    ),
    "custom_agent_tools": ScenarioDefaults(
        DEFAULT_CUSTOM_AGENT_TOOLS_REPORT_PATH,
        DEFAULT_CUSTOM_AGENT_TOOLS_SSE_PATH,
    ),
    "architected_frontend_group_chat_repair": ScenarioDefaults(
        DEFAULT_ARCHITECTED_FRONTEND_GROUP_CHAT_REPORT_PATH,
        DEFAULT_ARCHITECTED_FRONTEND_GROUP_CHAT_SSE_PATH,
        DEFAULT_ARCHITECTED_FRONTEND_GROUP_CHAT_BROWSER_REPORT_PATH,
    ),
    "group_process_document_strategy": ScenarioDefaults(
        DEFAULT_GROUP_PROCESS_DOCUMENT_STRATEGY_REPORT_PATH,
        DEFAULT_GROUP_PROCESS_DOCUMENT_STRATEGY_SSE_PATH,
    ),
    "group_process_data_analysis": ScenarioDefaults(
        DEFAULT_GROUP_PROCESS_DATA_ANALYSIS_REPORT_PATH,
        DEFAULT_GROUP_PROCESS_DATA_ANALYSIS_SSE_PATH,
    ),
    "group_process_workflow_delivery": ScenarioDefaults(
        DEFAULT_GROUP_PROCESS_WORKFLOW_DELIVERY_REPORT_PATH,
        DEFAULT_GROUP_PROCESS_WORKFLOW_DELIVERY_SSE_PATH,
    ),
    "group_process_failure_readable": ScenarioDefaults(
        DEFAULT_GROUP_PROCESS_FAILURE_READABLE_REPORT_PATH,
        DEFAULT_GROUP_PROCESS_FAILURE_READABLE_SSE_PATH,
    ),
    "group_process_frontend_preview": ScenarioDefaults(
        DEFAULT_GROUP_PROCESS_FRONTEND_PREVIEW_REPORT_PATH,
        DEFAULT_GROUP_PROCESS_FRONTEND_PREVIEW_SSE_PATH,
        DEFAULT_GROUP_PROCESS_FRONTEND_PREVIEW_BROWSER_REPORT_PATH,
    ),
    "agent_fallback_matrix": ScenarioDefaults(
        DEFAULT_AGENT_FALLBACK_MATRIX_REPORT_PATH,
        DEFAULT_AGENT_FALLBACK_MATRIX_SSE_PATH,
    ),
    "command_fulfillment_cyberpunk_group_deploy": ScenarioDefaults(
        DEFAULT_COMMAND_FULFILLMENT_REPORT_PATH,
        DEFAULT_COMMAND_FULFILLMENT_SSE_PATH,
        DEFAULT_COMMAND_FULFILLMENT_BROWSER_REPORT_PATH,
    ),
    "orchestrator_context_followup_repair": ScenarioDefaults(
        DEFAULT_CONTEXT_FOLLOWUP_REPORT_PATH,
        DEFAULT_CONTEXT_FOLLOWUP_SSE_PATH,
        DEFAULT_CONTEXT_FOLLOWUP_BROWSER_REPORT_PATH,
    ),
    "presentation_collapse_markers_smoke": ScenarioDefaults(
        DEFAULT_PRESENTATION_MARKERS_REPORT_PATH,
        DEFAULT_PRESENTATION_MARKERS_SSE_PATH,
        DEFAULT_PRESENTATION_MARKERS_BROWSER_REPORT_PATH,
    ),
    "group_dialogue_debate_no_artifacts": ScenarioDefaults(
        DEFAULT_GROUP_DIALOGUE_DEBATE_REPORT_PATH,
        DEFAULT_GROUP_DIALOGUE_DEBATE_SSE_PATH,
    ),
    "group_substantive_output_matrix": ScenarioDefaults(
        DEFAULT_GROUP_SUBSTANTIVE_OUTPUT_MATRIX_REPORT_PATH,
        DEFAULT_GROUP_SUBSTANTIVE_OUTPUT_MATRIX_SSE_PATH,
    ),
    "agent_turn_taking_dialogue_repair": ScenarioDefaults(
        DEFAULT_AGENT_TURN_TAKING_DIALOGUE_REPORT_PATH,
        DEFAULT_AGENT_TURN_TAKING_DIALOGUE_SSE_PATH,
    ),
    "agent_turn_taking_matrix": ScenarioDefaults(
        DEFAULT_AGENT_TURN_TAKING_MATRIX_REPORT_PATH,
        DEFAULT_AGENT_TURN_TAKING_MATRIX_SSE_PATH,
    ),
    "manual_two_agent_turn_taking": ScenarioDefaults(
        DEFAULT_MANUAL_TWO_AGENT_TURN_TAKING_REPORT_PATH,
        DEFAULT_MANUAL_TWO_AGENT_TURN_TAKING_SSE_PATH,
    ),
    "p1_attribution": ScenarioDefaults(
        DEFAULT_P1_ATTRIBUTION_REPORT_PATH,
        DEFAULT_P1_ATTRIBUTION_SSE_PATH,
    ),
    "p1_workflow": ScenarioDefaults(
        DEFAULT_P1_WORKFLOW_REPORT_PATH,
        DEFAULT_P1_WORKFLOW_SSE_PATH,
    ),
    "p1_workflow_runtime": ScenarioDefaults(
        DEFAULT_P1_WORKFLOW_RUNTIME_REPORT_PATH,
        DEFAULT_P1_WORKFLOW_RUNTIME_SSE_PATH,
    ),
    "p1_review_thread_repair": ScenarioDefaults(
        DEFAULT_P1_REVIEW_THREAD_REPORT_PATH,
        DEFAULT_P1_REVIEW_THREAD_SSE_PATH,
    ),
    "p1_rich_artifacts": ScenarioDefaults(
        DEFAULT_P1_RICH_ARTIFACTS_REPORT_PATH,
        DEFAULT_P1_RICH_ARTIFACTS_SSE_PATH,
    ),
    "p1_evaluation_repair": ScenarioDefaults(
        DEFAULT_P1_EVALUATION_REPAIR_REPORT_PATH,
        DEFAULT_P1_EVALUATION_REPAIR_SSE_PATH,
    ),
    "p1_agent_capability_profile": ScenarioDefaults(
        DEFAULT_P1_AGENT_CAPABILITY_PROFILE_REPORT_PATH,
        DEFAULT_P1_AGENT_CAPABILITY_PROFILE_SSE_PATH,
    ),
    "p2_agent_capability_profile_v2": ScenarioDefaults(
        DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_REPORT_PATH,
        DEFAULT_P2_AGENT_CAPABILITY_PROFILE_V2_SSE_PATH,
    ),
}


@dataclass(frozen=True)
class E2ESettings:
    base_url: str
    username: str
    password: str
    scenario: str
    report_path: Path
    sse_path: Path
    browser_report_path: Path
    prompt_override: str | None
    expect_container_status: str
    container_poll_timeout_seconds: float
    container_poll_interval_seconds: float
    use_temporary_user: bool


def validate_container_status_expectation(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in CONTAINER_STATUS_EXPECTATIONS:
        raise ValueError(
            "AGENTHUB_E2E_EXPECT_CONTAINER_STATUS must be not_supported, published, or any"
        )
    return normalized


def defaults_for_scenario(scenario: str) -> ScenarioDefaults:
    return SCENARIO_DEFAULTS.get(scenario, SCENARIO_DEFAULTS[DEFAULT_SCENARIO])


def load_settings(env: Mapping[str, str] | None = None) -> E2ESettings:
    source = os.environ if env is None else env
    scenario = source.get("AGENTHUB_E2E_SCENARIO", DEFAULT_SCENARIO).strip().lower()
    defaults = defaults_for_scenario(scenario)
    return E2ESettings(
        base_url=source.get("AGENTHUB_E2E_BASE_URL", DEFAULT_BASE_URL),
        username=source.get("AGENTHUB_E2E_USERNAME", DEFAULT_USERNAME),
        password=source.get("AGENTHUB_E2E_PASSWORD", DEFAULT_PASSWORD),
        scenario=scenario,
        report_path=Path(source.get("AGENTHUB_E2E_REPORT_PATH", defaults.report_path)),
        sse_path=Path(source.get("AGENTHUB_E2E_SSE_PATH", defaults.sse_path)),
        browser_report_path=Path(
            source.get("AGENTHUB_E2E_BROWSER_REPORT_PATH", defaults.browser_report_path)
        ),
        prompt_override=source.get("AGENTHUB_E2E_PROMPT"),
        expect_container_status=validate_container_status_expectation(
            source.get("AGENTHUB_E2E_EXPECT_CONTAINER_STATUS", "published")
        ),
        container_poll_timeout_seconds=float(
            source.get("AGENTHUB_E2E_CONTAINER_POLL_TIMEOUT_SECONDS", "180")
        ),
        container_poll_interval_seconds=float(
            source.get("AGENTHUB_E2E_CONTAINER_POLL_INTERVAL_SECONDS", "2")
        ),
        use_temporary_user=(
            scenario == "p2_agent_capability_profile_v2"
            and "AGENTHUB_E2E_USERNAME" not in source
        ),
    )
