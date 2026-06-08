"""Deterministic checks for whether a sub-agent actually completed its task."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from app.agents.orchestrator._internal.execution.summary import (
    truncate_preserving_edges,
)
from app.agents.orchestrator.types import SubTask, TaskAttempt

MIN_TEXT_CHARS = 80
MIN_REVIEW_CHARS = 50
SUMMARY_MAX_CHARS = 1800

HOST_ONLY_PATTERNS = (
    r"请.*登场",
    r"下面有请",
    r"有请.+发言",
    r"我来主持",
    r"作为主持",
    r"辩论正式开始",
    r"讨论正式开始",
    r"请.*发表",
    r"轮到你了",
    r"该你了",
)
GENERIC_DONE_PATTERNS = (
    r"^已完成[:：]?.{0,80}$",
    r"^完成[:：]?.{0,80}$",
    r"^done\.?$",
    r"^the delegated task did not complete successfully\.?$",
)
ANALYSIS_MARKERS = (
    "分析",
    "策略",
    "方案",
    "建议",
    "结论",
    "依据",
    "风险",
    "取舍",
    "brainstorm",
    "strategy",
    "analysis",
    "data",
)
REVIEW_MARKERS = (
    "通过",
    "未通过",
    "问题",
    "风险",
    "缺口",
    "建议",
    "修复",
    "pass",
    "fail",
    "gap",
    "risk",
    "repair",
    "needs_repair",
    "missing",
)


@dataclass(frozen=True, slots=True)
class OutputValidation:
    contract_type: str
    passed: bool
    reason: str = ""
    summary_text: str = ""


def validate_task_output(task: SubTask, attempt: TaskAttempt) -> OutputValidation:
    contract_type = output_contract_type(task, attempt)
    if contract_type in {"artifact", "platform"}:
        return OutputValidation(contract_type=contract_type, passed=True)
    if contract_type == "implementation":
        return _validate_implementation(attempt)
    if contract_type == "review":
        return _validate_review(task, attempt)
    if contract_type in {"conversation", "analysis", "direct_output"}:
        return _validate_textual(task, attempt, contract_type)
    return _validate_textual(task, attempt, contract_type)


def output_contract_type(task: SubTask, attempt: TaskAttempt | None = None) -> str:
    haystack = (
        f"{task.task_id} {task.title} {task.instruction} "
        f"{task.expected_output or ''}"
    ).lower()
    if task.task_type == "conversation":
        return "conversation"
    if task.task_type == "review":
        return "review"
    if task.task_id.startswith("direct-"):
        return "direct_output"
    if attempt is not None and (attempt.artifact_paths or attempt.tool_summaries):
        return "artifact"
    if _expected_output_has_artifact(task.expected_output):
        return "artifact"
    if any(marker in haystack for marker in ANALYSIS_MARKERS):
        return "analysis"
    return "implementation"


def correction_task(task: SubTask, validation: OutputValidation) -> SubTask:
    instruction = (
        "上一轮输出没有实质完成 Orchestrator 分配给你的任务。"
        f"\n不通过原因：{validation.reason or '缺少实质输出'}"
        "\n\n请立刻重新完成同一个任务。硬性要求："
        "\n- 直接完成你被分配的角色、分析、实现或审阅。"
        "\n- 不要主持、不要邀请别人登场、不要转述任务、不要只说已完成。"
        "\n- 如果这是对话/辩论/角色扮演任务，必须直接以你的指定身份发言。"
        "\n- 如果这是分析/策略/数据任务，必须给出结论、依据和建议。"
        "\n- 如果这是审阅任务，必须说明 pass/fail、问题或 gaps。"
        "\n- 除非原任务要求生成文件，否则不要创建 workspace 文件。"
        "\n\n原始任务：\n"
        f"{task.instruction}"
    )
    return replace(task, instruction=instruction)


def visible_summary_from_attempt(task: SubTask, attempt: TaskAttempt) -> str:
    validation = validate_task_output(task, attempt)
    if validation.summary_text:
        return validation.summary_text
    return truncate_preserving_edges(attempt.text_preview, SUMMARY_MAX_CHARS) + "\n"


def _validate_textual(
    task: SubTask,
    attempt: TaskAttempt,
    contract_type: str,
) -> OutputValidation:
    text = _visible_text(attempt)
    if not text:
        return OutputValidation(
            contract_type=contract_type,
            passed=False,
            reason="没有可见文本输出。",
        )
    if _looks_generic_done(text):
        return OutputValidation(
            contract_type=contract_type,
            passed=False,
            reason="输出只是空泛完成语，没有实质内容。",
        )
    if contract_type == "conversation" and _looks_like_host_only(text):
        return OutputValidation(
            contract_type=contract_type,
            passed=False,
            reason="输出像主持或邀请发言，没有以分配角色直接发言。",
        )
    min_chars = 20 if contract_type == "direct_output" else MIN_TEXT_CHARS
    if len(text) < min_chars:
        return OutputValidation(
            contract_type=contract_type,
            passed=False,
            reason="输出过短，缺少可验证的实质内容。",
        )
    if contract_type == "conversation" and not _conversation_role_satisfied(task, text):
        return OutputValidation(
            contract_type=contract_type,
            passed=False,
            reason="输出没有体现本任务指定的角色、立场或对话主题。",
        )
    summary_text = _clean_textual_summary(task, text, contract_type)
    summary = truncate_preserving_edges(summary_text, SUMMARY_MAX_CHARS) + "\n"
    return OutputValidation(contract_type=contract_type, passed=True, summary_text=summary)


def _validate_review(task: SubTask, attempt: TaskAttempt) -> OutputValidation:
    if attempt.artifact_paths:
        artifacts = "、".join(attempt.artifact_paths[:6])
        summary = (
            f"Review passed: {_clean_review_subject(task)} 已完成审阅。"
            "未发现阻断性 gaps；可继续使用当前产物。"
        )
        if artifacts:
            summary += f"\n审阅产物：{artifacts}。"
        return OutputValidation(
            contract_type="review",
            passed=True,
            summary_text=truncate_preserving_edges(summary, SUMMARY_MAX_CHARS) + "\n",
        )
    text = _visible_text(attempt)
    if len(text) < MIN_REVIEW_CHARS:
        return OutputValidation(
            contract_type="review",
            passed=False,
            reason="审阅输出过短，缺少结论或问题说明。",
        )
    lowered = text.lower()
    if not any(marker in lowered for marker in REVIEW_MARKERS):
        return OutputValidation(
            contract_type="review",
            passed=False,
            reason="审阅输出缺少 pass/fail、问题、风险或 gaps。",
        )
    return OutputValidation(
        contract_type="review",
        passed=True,
        summary_text=truncate_preserving_edges(text, SUMMARY_MAX_CHARS) + "\n",
    )


def _clean_review_subject(task: SubTask) -> str:
    subject = task.title.strip() or "本阶段产物"
    subject = re.sub(r"\s+", " ", subject)
    return subject[:120]


def _clean_textual_summary(task: SubTask, text: str, contract_type: str) -> str:
    if contract_type == "conversation":
        return _clean_conversation_summary(text)
    return _strip_prompt_echo(task, text)


def _strip_prompt_echo(task: SubTask, text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return compact
    markers = (
        "两位智能体的头脑风暴结果汇总如下",
        "渠道预算分配分析报告",
        "核心结论",
        "结论：",
        "建议1",
        "建议 1",
        "**1.",
        "1. **",
        "策略一",
        "策略 1",
        "## ",
        "### ",
    )
    prompt_markers = (
        "请直接输出",
        "请保持简洁",
        "以下是背景",
        "你正在参加",
        "不要写完整",
        "原始任务",
    )
    for marker in markers:
        idx = compact.find(marker)
        if idx <= 0:
            continue
        prefix = compact[:idx]
        suffix = compact[idx:].strip()
        if len(suffix) >= 40 and (
            any(item in prefix for item in prompt_markers)
            or task.instruction[:40] in prefix
        ):
            return suffix
    return compact


def _validate_implementation(attempt: TaskAttempt) -> OutputValidation:
    if attempt.artifact_paths or attempt.tool_summaries:
        return OutputValidation(contract_type="implementation", passed=True)
    if _visible_text(attempt):
        return OutputValidation(contract_type="implementation", passed=True)
    return OutputValidation(
        contract_type="implementation",
        passed=False,
        reason="没有可见输出、工具证据或产物。",
    )


def _visible_text(attempt: TaskAttempt) -> str:
    return re.sub(r"\s+", " ", attempt.text_preview or "").strip()


def _looks_like_host_only(text: str) -> bool:
    compact = text.strip()
    if _has_substantive_conversation_marker(compact):
        return False
    if len(compact) > 240:
        return False
    return any(re.search(pattern, compact, re.I) for pattern in HOST_ONLY_PATTERNS)


def _looks_generic_done(text: str) -> bool:
    compact = text.strip()
    return any(re.search(pattern, compact, re.I) for pattern in GENERIC_DONE_PATTERNS)


def _conversation_role_satisfied(task: SubTask, text: str) -> bool:
    title = task.title
    instruction = task.instruction
    if "反方" in title or re.search(r"(以|作为)?反方(身份|观点|发言)?", instruction):
        return "弊大于利" in text or "反方" in text
    if "正方" in title or re.search(r"(以|作为)?正方(身份|观点|发言)?", instruction):
        return "利大于弊" in text or "正方" in text
    if "弊大于利" in title:
        return "弊大于利" in text or "反方" in text
    if "利大于弊" in title:
        return "利大于弊" in text or "正方" in text
    haystack = f"{title} {instruction}"
    has_positive_topic = "利大于弊" in haystack
    has_negative_topic = "弊大于利" in haystack
    if has_positive_topic and not has_negative_topic:
        return "利大于弊" in text or "正方" in text
    if has_negative_topic and not has_positive_topic:
        return "弊大于利" in text or "反方" in text
    if "角色" in haystack:
        return "我" in text or "角色" in text
    return True


def _has_substantive_conversation_marker(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "正方观点",
            "反方观点",
            "我认为",
            "核心观点",
            "我的立场",
            "主要理由",
            "结论是",
        )
    )


def _clean_conversation_summary(text: str) -> str:
    parts = [
        part.strip()
        for part in re.split(r"(?<=[。.!?！？])", text)
        if part.strip()
    ]
    cleaned = [
        part
        for part in parts
        if not any(re.search(pattern, part, re.I) for pattern in HOST_ONLY_PATTERNS)
        and not _looks_generic_done(part)
    ]
    if cleaned:
        return "".join(cleaned)
    return text


def _expected_output_has_artifact(expected_output: str | None) -> bool:
    if not expected_output:
        return False
    return bool(
        re.search(
            r"[\w./-]+\\.(?:html|css|js|ts|tsx|jsx|md|json|yaml|yml|py|txt|csv|pptx|zip)",
            expected_output,
            re.I,
        )
    )
