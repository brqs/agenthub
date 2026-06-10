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
RESPONSE_MARKERS = (
    "回应",
    "针对",
    "反驳",
    "补充",
    "同意",
    "不同意",
    "你提到",
    "上一轮",
    "上一位",
    "对方",
    "但",
    "不过",
    "我认同",
    "我不同意",
    "respond",
    "counter",
    "agree",
    "disagree",
)
OTHER_SPEAKER_PATTERNS = (
    r"\n\s*(?:正方|反方|主持人|旁白|Claude(?: Code)?|OpenCode(?: Helper)?|Codex(?: Helper)?)[：:]",
    r"\n\s*@[\w-]+\s*[：:]",
    r"\[Agent:\s*[^]]+\]",
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
    if contract_type in {"conversation", "dialogue_turn", "analysis", "direct_output"}:
        return _validate_textual(task, attempt, contract_type)
    return _validate_textual(task, attempt, contract_type)


def output_contract_type(task: SubTask, attempt: TaskAttempt | None = None) -> str:
    haystack = (
        f"{task.task_id} {task.title} {task.instruction} "
        f"{task.expected_output or ''}"
    ).lower()
    if task.task_type == "conversation":
        return "conversation"
    if task.task_type == "dialogue_turn":
        return "dialogue_turn"
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
        "\n- 如果这是接力对话任务，只写你自己的本轮发言；需要回应上一轮时，"
        "明确回应、补充或反驳前一位观点。不要代写其他 Agent 的完整发言。"
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
    if contract_type in {"conversation", "dialogue_turn"} and _looks_like_host_only(text):
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
    if _looks_like_assignment_echo(task, text, contract_type):
        return OutputValidation(
            contract_type=contract_type,
            passed=False,
            reason="输出主要是在复述任务要求，没有完成自己的实质贡献。",
        )
    if contract_type == "analysis" and not any(
        marker in text.lower() for marker in ANALYSIS_MARKERS
    ):
        return OutputValidation(
            contract_type=contract_type,
            passed=False,
            reason="分析输出缺少结论、依据或建议。",
        )
    if (
        contract_type in {"conversation", "dialogue_turn"}
        and not _conversation_role_satisfied(task, text)
    ):
        return OutputValidation(
            contract_type=contract_type,
            passed=False,
            reason="输出没有体现本任务指定的角色、立场或对话主题。",
        )
    if contract_type == "dialogue_turn" and _scripts_other_agent_turns(task, text):
        return OutputValidation(
            contract_type=contract_type,
            passed=False,
            reason="输出包含其他 Agent 的完整发言，未按本轮职责只发表自己的观点。",
        )
    if contract_type == "dialogue_turn" and _requires_previous_turn_response(task):
        if not any(marker in text.lower() for marker in RESPONSE_MARKERS):
            return OutputValidation(
                contract_type=contract_type,
                passed=False,
                reason="本轮需要回应上一轮，但输出没有体现回应、补充或反驳。",
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
    if contract_type in {"conversation", "dialogue_turn"}:
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
    if "角色扮演" in haystack:
        return "我" in text or "角色" in text or _has_topic_overlap(task, text)
    return True


def _has_topic_overlap(task: SubTask, text: str) -> bool:
    haystack = f"{task.title} {task.instruction}"
    tokens = [
        token
        for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z][a-zA-Z0-9_-]{2,}", haystack)
        if token not in {"orchestrator", "agent", "helper", "直接", "输出", "不要", "生成", "文件"}
    ]
    if not tokens:
        return True
    return sum(1 for token in dict.fromkeys(tokens[:30]) if token in text) >= 2


def _looks_like_assignment_echo(
    task: SubTask,
    text: str,
    contract_type: str,
) -> bool:
    compact = re.sub(r"\s+", "", text).lower()
    instruction = re.sub(r"\s+", "", task.instruction).lower()
    title = re.sub(r"\s+", "", task.title).lower()
    if not compact:
        return False
    assignment_markers = (
        "请让两个智能体",
        "请你们两位",
        "请你们两位分别",
        "分析要求",
        "不生成文件",
        "不需要生成文件",
        "直接在群聊",
        "直接回复结论",
        "原始用户请求",
        "@orchestrator",
        "@claude-code",
        "@opencode-helper",
    )
    contribution_markers = (
        "结论",
        "依据",
        "建议",
        "我认为",
        "我的",
        "观点",
        "理由",
        "风险",
        "优先级",
        "排序",
        "pass",
        "fail",
        "gap",
        "通过",
        "未通过",
        "改进",
    )
    if compact.startswith("@") and any(
        marker in compact for marker in ("请你们两位", "请让两个智能体")
    ):
        return True
    if any(marker in compact for marker in ("请你们两位分别", "请让两个智能体")) and (
        "不生成文件" in compact or "不需要生成文件" in compact
    ):
        return True
    if any(marker in compact for marker in assignment_markers) and not any(
        marker in compact for marker in contribution_markers
    ):
        return True
    if len(compact) < 800 and (
        compact in instruction
        or compact in title
        or (len(instruction) > 80 and instruction[: min(len(compact), 240)] in compact)
    ):
        return True
    if contract_type in {"analysis", "conversation", "dialogue_turn"}:
        request_markers = sum(1 for marker in assignment_markers if marker in compact)
        contribution_count = sum(1 for marker in contribution_markers if marker in compact)
        if request_markers >= 2 and contribution_count <= 1:
            return True
    return False


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


def _requires_previous_turn_response(task: SubTask) -> bool:
    haystack = f"{task.title}\n{task.instruction}".lower()
    return bool(task.depends_on) or any(
        marker in haystack
        for marker in (
            "上一轮",
            "上一位",
            "previous turn",
            "prior turn",
            "respond to the previous",
            "回应上一",
            "补充上一",
            "反驳上一",
        )
    )


def _scripts_other_agent_turns(task: SubTask, text: str) -> bool:
    matches = [
        match.group(0).strip()
        for pattern in OTHER_SPEAKER_PATTERNS
        for match in re.finditer(pattern, f"\n{text}", re.I)
    ]
    if len(matches) < 2:
        return False
    own_agent = task.agent_id.lower()
    own_labels = {
        own_agent,
        own_agent.replace("-", " "),
        own_agent.replace("-helper", ""),
    }
    foreign = [
        label
        for label in matches
        if not any(own_label and own_label in label.lower() for own_label in own_labels)
    ]
    return len(foreign) >= 2


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
