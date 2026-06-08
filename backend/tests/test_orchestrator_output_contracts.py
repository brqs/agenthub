from __future__ import annotations

from app.agents.orchestrator._internal.execution.output_contracts import (
    validate_task_output,
)
from app.agents.orchestrator.types import SubTask, TaskAttempt


def _task(
    *,
    task_type: str = "implementation",
    title: str = "Task",
    instruction: str = "Complete the task.",
    expected_output: str | None = None,
) -> SubTask:
    return SubTask(
        task_id="task-1",
        agent_id="agent-a",
        title=title,
        instruction=instruction,
        expected_output=expected_output,
        task_type=task_type,
    )


def _attempt(text: str = "", artifacts: list[str] | None = None) -> TaskAttempt:
    return TaskAttempt(
        attempt_index=1,
        agent_id="agent-a",
        text_preview=text,
        artifact_paths=list(artifacts or []),
    )


def test_conversation_contract_rejects_host_only_and_cleans_corrected_summary() -> None:
    task = _task(
        task_type="conversation",
        title="正方发言：AI 快速发展利大于弊",
        instruction="直接以正方身份发言，不要主持或邀请别人。",
    )

    failed = validate_task_output(task, _attempt("辩论正式开始！正方一辩请登场。"))
    assert not failed.passed
    assert failed.contract_type == "conversation"

    passed = validate_task_output(
        task,
        _attempt(
            "辩论正式开始！正方一辩请登场。"
            "正方观点：我认为 AI 快速发展利大于弊，因为它能提升医疗、"
            "教育和生产效率，同时风险可以通过监管和责任追踪缓解。"
            "对于中小企业和公共服务来说，AI 还能降低专业能力门槛，"
            "让更多人获得高质量辅助决策。"
        ),
    )
    assert passed.passed
    assert "请登场" not in passed.summary_text
    assert "正方观点" in passed.summary_text


def test_analysis_contract_requires_substantive_text() -> None:
    task = _task(
        title="Analyze onboarding strategy",
        instruction="分析 AgentHub 新用户 onboarding 策略，给出结论和依据。",
    )

    failed = validate_task_output(task, _attempt("已完成"))
    assert not failed.passed

    passed = validate_task_output(
        task,
        _attempt(
            "结论：新用户 onboarding 应优先降低首次创建 Agent 的门槛。"
            "依据是用户最早流失通常发生在配置模型和理解工作区能力之前，"
            "因此建议提供模板、默认模型检查和首轮任务示例，同时提示潜在风险。"
        ),
    )
    assert passed.passed
    assert passed.contract_type == "analysis"


def test_analysis_contract_strips_prompt_echo_from_summary() -> None:
    task = _task(
        title="AgentHub Onboarding 策略头脑风暴",
        instruction=(
            "你正在参加 AgentHub 新用户 onboarding 策略的头脑风暴。"
            "请直接输出你的具体建议、理由和风险。"
        ),
    )

    validation = validate_task_output(
        task,
        _attempt(
            "你正在参加 AgentHub 新用户 onboarding 策略的头脑风暴。"
            "请直接输出你的具体建议、理由和风险。以下是背景：AgentHub。"
            "两位智能体的头脑风暴结果汇总如下：建议1：提供模板库。"
            "理由：降低首次使用门槛。风险：模板质量需要持续维护。"
        ),
    )

    assert validation.passed
    assert "请直接输出" not in validation.summary_text
    assert "以下是背景" not in validation.summary_text
    assert "两位智能体的头脑风暴结果汇总如下" in validation.summary_text


def test_artifact_contract_accepts_file_evidence_without_text_summary() -> None:
    task = _task(
        title="Build static page",
        instruction="创建 index.html、styles.css 和 app.js。",
        expected_output="index.html, styles.css, app.js",
    )

    validation = validate_task_output(
        task,
        _attempt("", ["index.html", "styles.css", "app.js"]),
    )
    assert validation.passed
    assert validation.contract_type == "artifact"


def test_review_contract_requires_pass_fail_or_gaps_when_no_review_file() -> None:
    task = _task(
        task_type="review",
        title="Review implementation",
        instruction="审阅前端实现，说明 pass/fail 或 gaps。",
    )

    failed = validate_task_output(task, _attempt("已审阅，完成。"))
    assert not failed.passed

    passed = validate_task_output(
        task,
        _attempt(
            "Review result: pass with gaps. 主要问题是移动端按钮间距偏小，"
            "建议补充 480px 断点验证；没有发现阻断发布的风险。"
        ),
    )
    assert passed.passed
    assert passed.contract_type == "review"


def test_review_contract_generates_substantive_summary_from_artifacts() -> None:
    task = _task(
        task_type="review",
        title="检查产物并总结变更",
        instruction="检查 index.html、styles.css、app.js 并总结变更。",
    )

    validation = validate_task_output(
        task,
        _attempt("", ["index.html", "styles.css", "app.js"]),
    )

    assert validation.passed
    assert validation.contract_type == "review"
    assert "Review passed" in validation.summary_text
    assert "gaps" in validation.summary_text
    assert "index.html" in validation.summary_text
