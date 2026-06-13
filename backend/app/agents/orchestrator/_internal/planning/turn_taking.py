"""Turn-taking intent helpers for Orchestrator-managed group dialogue."""

from __future__ import annotations

from collections.abc import Iterable

TURN_TAKING_MARKERS = (
    "轮流",
    "一人一句",
    "一人一轮",
    "一轮一轮",
    "接力",
    "回应对方",
    "回复对方",
    "反驳对方",
    "互相回应",
    "互相反驳",
    "互相 review",
    "互相评审",
    "展开辩论",
    "继续辩论",
    "让他回复",
    "@其他agent",
    "@另一个agent",
    "turn-taking",
    "take turns",
    "one by one",
    "respond to each other",
)

NO_ARTIFACT_DIALOGUE_MARKERS = (
    "不需要生成文件",
    "不要生成文件",
    "不生成文件",
    "不要写文件",
    "无需文件",
    "直接对话",
    "对话形式",
    "群聊发言",
    "no files",
    "no artifact",
    "no artifacts",
)

ARTIFACT_INTENT_MARKERS = (
    "生成文件",
    "创建文件",
    "写文件",
    "生成文档",
    "写文档",
    "文档",
    "报告",
    "代码",
    "网站",
    "网页",
    "前端",
    "后端",
    "实现",
    "开发",
    "部署",
    "预览",
    "文件",
    "产物",
    "artifact",
    "file",
    "document",
    "report",
    "code",
    "website",
    "frontend",
    "backend",
    "deploy",
    "preview",
)

STANDALONE_DIALOGUE_START_MARKERS = (
    "开始一场",
    "来一场",
    "组织一场",
    "开展一场",
    "进行一场",
    "发起一场",
    "start a",
    "host a",
    "run a",
)

STANDALONE_DIALOGUE_TOPIC_MARKERS = (
    "辩论",
    "讨论",
    "对话",
    "圆桌",
    "利弊",
    "利处",
    "弊处",
    "优缺点",
    "正方",
    "反方",
    "pros and cons",
    "benefits and risks",
    "advantages and disadvantages",
)

MULTI_AGENT_DIALOGUE_MARKERS = (
    "两个智能体",
    "两个 agent",
    "两个可用 agent",
    "两位智能体",
    "两位 agent",
    "多个智能体",
    "多智能体",
    "多个 agent",
    "分别",
    "各自",
    "每个智能体",
    "每位",
    "协作讨论",
    "协作分析",
    "群组内",
)

DIALOGUE_COLLABORATION_MARKERS = (
    "辩论",
    "对话",
    "群聊",
    "群组",
    "圆桌",
    "角色扮演",
    "头脑风暴",
    "观点对比",
    "方案评审",
    "代码 review",
    "代码审查",
    "评审",
    "审查",
    "数据分析",
    "分析这组数据",
    "分析数据",
    "策略",
    "建议",
    "需求澄清",
    "review",
    "panel",
    "debate",
    "roundtable",
    "roleplay",
    "role-play",
    "brainstorm",
    "review panel",
    "data panel",
)


def turn_taking_requested(text: str) -> bool:
    """Return True when a request asks agents to speak in managed turns."""

    normalized = text.lower()
    has_dialogue_context = any(
        marker in normalized for marker in DIALOGUE_COLLABORATION_MARKERS
    )
    if not has_dialogue_context:
        return False
    return any(marker in normalized for marker in TURN_TAKING_MARKERS) or any(
        marker in normalized for marker in MULTI_AGENT_DIALOGUE_MARKERS
    )


def pure_dialogue_requested(text: str) -> bool:
    """Return True when the request is best handled as no-artifact group dialogue."""

    normalized = text.lower()
    if not normalized.strip():
        return False
    if any(marker in normalized for marker in NO_ARTIFACT_DIALOGUE_MARKERS):
        return any(
            marker in normalized
            for marker in (*DIALOGUE_COLLABORATION_MARKERS, *STANDALONE_DIALOGUE_TOPIC_MARKERS)
        )
    if any(marker in normalized for marker in ARTIFACT_INTENT_MARKERS):
        return False
    if turn_taking_requested(text):
        return True
    has_dialogue_start = any(
        marker in normalized for marker in STANDALONE_DIALOGUE_START_MARKERS
    )
    has_dialogue_topic = any(
        marker in normalized for marker in STANDALONE_DIALOGUE_TOPIC_MARKERS
    )
    return has_dialogue_start and has_dialogue_topic


def should_route_group_turn_taking_to_orchestrator(
    *,
    text: str,
    conversation_agent_ids: Iterable[str],
    target_agent_id: str | None,
) -> bool:
    """Detect direct-target group requests that require Orchestrator mediation."""

    participant_ids = [
        agent_id
        for agent_id in conversation_agent_ids
        if isinstance(agent_id, str) and agent_id and agent_id != "orchestrator"
    ]
    if len(dict.fromkeys(participant_ids)) < 2:
        return False
    if target_agent_id == "orchestrator":
        return False
    return pure_dialogue_requested(text)
