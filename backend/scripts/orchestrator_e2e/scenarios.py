"""Scenario registry and stable scenario metadata."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import runner
from .config import SCENARIO_DEFAULTS
from .evaluators import (
    evaluate_p1_agent_capability_profile,
    evaluate_p1_evaluation_repair,
    evaluate_p1_rich_artifacts,
    evaluate_p2_agent_capability_profile_v2,
    preserve_existing_acceptance,
)

ScenarioRunner = Callable[..., None]
ScenarioEvaluator = Callable[[dict[str, Any]], None]
QUALITY_PROMPT = (
    "@orchestrator 帮我完成一个带任务拆解、代码产物、Diff、网页预览、按钮交互和移动端适配的"
    "前端开发演示，主题随机，部署在端口8082，并完成浏览器级质量验收"
)


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    prompt: str
    agent_ids: tuple[str, ...]
    default_report_path: Path
    default_sse_path: Path
    default_browser_report_path: Path
    runner: ScenarioRunner
    evaluator: ScenarioEvaluator
    use_temporary_user: bool = False


def _spec(
    name: str,
    prompt: str,
    scenario_runner: ScenarioRunner,
    evaluator: ScenarioEvaluator = preserve_existing_acceptance,
    *,
    agent_ids: list[str] | None = None,
    use_temporary_user: bool = False,
) -> ScenarioSpec:
    defaults = SCENARIO_DEFAULTS[name]
    return ScenarioSpec(
        name=name,
        prompt=prompt,
        agent_ids=tuple(agent_ids or runner.AGENT_IDS),
        default_report_path=Path(defaults.report_path),
        default_sse_path=Path(defaults.sse_path),
        default_browser_report_path=Path(defaults.browser_report_path),
        runner=scenario_runner,
        evaluator=evaluator,
        use_temporary_user=use_temporary_user,
    )


SCENARIOS: dict[str, ScenarioSpec] = {
    "quality": _spec("quality", QUALITY_PROMPT, runner.main),
    "architected_frontend_group_chat_repair": _spec(
        "architected_frontend_group_chat_repair",
        QUALITY_PROMPT,
        runner.main,
    ),
    "group_process_document_strategy": _spec(
        "group_process_document_strategy",
        runner.GROUP_PROCESS_DOCUMENT_STRATEGY_PROMPT,
        runner.run_generic_group_process_case,
    ),
    "group_process_data_analysis": _spec(
        "group_process_data_analysis",
        runner.GROUP_PROCESS_DATA_ANALYSIS_PROMPT,
        runner.run_generic_group_process_case,
    ),
    "group_process_workflow_delivery": _spec(
        "group_process_workflow_delivery",
        runner.GROUP_PROCESS_WORKFLOW_DELIVERY_PROMPT,
        runner.run_generic_group_process_case,
    ),
    "group_process_failure_readable": _spec(
        "group_process_failure_readable",
        runner.GROUP_PROCESS_FAILURE_READABLE_PROMPT,
        runner.run_generic_group_process_case,
    ),
    "group_process_frontend_preview": _spec(
        "group_process_frontend_preview",
        QUALITY_PROMPT,
        runner.main,
    ),
    "agent_fallback_matrix": _spec(
        "agent_fallback_matrix",
        runner.AGENT_FALLBACK_MATRIX_PROMPT,
        runner.run_agent_fallback_matrix_case,
    ),
    "command_fulfillment_cyberpunk_group_deploy": _spec(
        "command_fulfillment_cyberpunk_group_deploy",
        runner.COMMAND_FULFILLMENT_PROMPT,
        runner.main,
    ),
    "orchestrator_context_followup_repair": _spec(
        "orchestrator_context_followup_repair",
        runner.COMMAND_FULFILLMENT_PROMPT,
        runner.main,
    ),
    "presentation_collapse_markers_smoke": _spec(
        "presentation_collapse_markers_smoke",
        runner.PRESENTATION_COLLAPSE_PROMPT,
        runner.run_presentation_collapse_case,
    ),
    "group_dialogue_debate_no_artifacts": _spec(
        "group_dialogue_debate_no_artifacts",
        runner.GROUP_DIALOGUE_DEBATE_PROMPT,
        runner.run_group_dialogue_debate_case,
    ),
    "group_substantive_output_matrix": _spec(
        "group_substantive_output_matrix",
        runner.GROUP_SUBSTANTIVE_OUTPUT_MATRIX_PROMPT,
        runner.run_group_substantive_output_matrix_case,
    ),
    "agent_turn_taking_dialogue_repair": _spec(
        "agent_turn_taking_dialogue_repair",
        runner.AGENT_TURN_TAKING_DIALOGUE_PROMPT,
        runner.run_group_dialogue_debate_case,
    ),
    "agent_turn_taking_matrix": _spec(
        "agent_turn_taking_matrix",
        runner.GROUP_SUBSTANTIVE_OUTPUT_MATRIX_PROMPT,
        runner.run_group_substantive_output_matrix_case,
    ),
    "manual_two_agent_turn_taking": _spec(
        "manual_two_agent_turn_taking",
        runner.MANUAL_TWO_AGENT_TURN_TAKING_PROMPT,
        runner.run_manual_two_agent_turn_taking_case,
    ),
    "fullstack": _spec("fullstack", runner.FULLSTACK_PROMPT, runner.main),
    "deployment": _spec("deployment", runner.DEPLOYMENT_PROMPT, runner.main),
    "deployment_repair": _spec(
        "deployment_repair",
        runner.DEPLOYMENT_REPAIR_PROMPT,
        runner.main,
    ),
    "custom_agent_tools": _spec(
        "custom_agent_tools",
        runner.CUSTOM_AGENT_TOOLS_PROMPT,
        runner.run_custom_agent_tools_case,
    ),
    "p1_attribution": _spec(
        "p1_attribution",
        runner.P1_ATTRIBUTION_PROMPT,
        runner.run_p1_case,
    ),
    "p1_workflow": _spec(
        "p1_workflow",
        runner.P1_WORKFLOW_PROMPT,
        runner.run_p1_case,
    ),
    "p1_workflow_runtime": _spec(
        "p1_workflow_runtime",
        runner.P1_WORKFLOW_RUNTIME_PROMPT,
        runner.run_p1_case,
    ),
    "p1_review_thread_repair": _spec(
        "p1_review_thread_repair",
        runner.P1_REVIEW_THREAD_PROMPT,
        runner.run_p1_case,
    ),
    "p1_rich_artifacts": _spec(
        "p1_rich_artifacts",
        runner.P1_RICH_ARTIFACTS_PROMPT,
        runner.run_p1_case,
        evaluate_p1_rich_artifacts,
    ),
    "p1_evaluation_repair": _spec(
        "p1_evaluation_repair",
        runner.P1_EVALUATION_REPAIR_PROMPT,
        runner.run_p1_case,
        evaluate_p1_evaluation_repair,
    ),
    "p1_agent_capability_profile": _spec(
        "p1_agent_capability_profile",
        runner.P1_AGENT_CAPABILITY_PROFILE_PROMPT,
        runner.run_p1_agent_capability_profile_case,
        evaluate_p1_agent_capability_profile,
        agent_ids=runner.P1_AGENT_CAPABILITY_PROFILE_AGENT_IDS,
    ),
    "p2_agent_capability_profile_v2": _spec(
        "p2_agent_capability_profile_v2",
        runner.P2_AGENT_CAPABILITY_PROFILE_V2_PROMPT,
        runner.run_p2_agent_capability_profile_v2_case,
        evaluate_p2_agent_capability_profile_v2,
        agent_ids=runner.P1_AGENT_CAPABILITY_PROFILE_AGENT_IDS,
        use_temporary_user=True,
    ),
}


def get_scenario(name: str) -> ScenarioSpec:
    return SCENARIOS[name]
