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


def test_dialogue_turn_contract_requires_own_turn_and_response() -> None:
    task = SubTask(
        task_id="turn-2",
        agent_id="opencode-helper",
        title="第 2 轮发言：反方",
        instruction=(
            "本轮必须明确回应上一轮，不要代写其他 Agent 的完整发言。"
            "你的角色/立场：反方，主张 AI 快速发展弊大于利。"
        ),
        depends_on=("turn-1",),
        task_type="dialogue_turn",
    )

    scripted = validate_task_output(
        task,
        _attempt(
            "正方：AI 能提升医疗和教育效率。\n"
            "反方：我认为风险更大。\n"
            "主持人：请继续。"
        ),
    )
    assert not scripted.passed
    assert scripted.contract_type == "dialogue_turn"

    no_response = validate_task_output(
        task,
        _attempt(
            "反方观点：我认为 AI 快速发展弊大于利，因为就业替代、隐私滥用"
            "和信息信任危机可能先于治理成熟，社会成本会被放大。"
        ),
    )
    assert not no_response.passed

    passed = validate_task_output(
        task,
        _attempt(
            "针对上一轮提到的医疗和教育效率，我同意 AI 有局部收益，"
            "但我的反方立场是快速发展总体弊大于利。原因是就业替代、"
            "隐私滥用和信息信任危机可能更早爆发，而治理制度通常滞后。"
            "如果收益集中在少数平台，普通人承担风险，社会整体会付出更高代价。"
        ),
    )
    assert passed.passed
    assert "针对上一轮" in passed.summary_text


def test_dialogue_turn_accepts_clear_negative_stance_without_fixed_phrase() -> None:
    task = SubTask(
        task_id="turn-2",
        agent_id="opencode-helper",
        title="第 2 轮发言：反方",
        instruction=(
            "本轮必须明确回应上一轮，不要代写其他 Agent 的完整发言。"
            "你的角色/立场：反方，主张 AI 快速发展弊大于利。"
        ),
        depends_on=("turn-1",),
        task_type="dialogue_turn",
    )

    validation = validate_task_output(
        task,
        _attempt(
            "针对 Claude-code 提到的医疗和教育收益，我承认这些例子有价值，"
            "但必须看到更大的社会风险。快速自动化会造成就业断层，"
            "深度伪造和信息操纵会削弱公共信任，隐私滥用与安全失控也会"
            "先于监管成熟出现。如果治理滞后，普通人承担的代价会超过少数"
            "平台获得的效率收益。"
        ),
    )

    assert validation.passed
    assert "就业断层" in validation.summary_text


def test_dialogue_turn_accepts_negative_distribution_and_speed_argument() -> None:
    task = SubTask(
        task_id="turn-2",
        agent_id="opencode-helper",
        title="第 2 轮发言：反方",
        instruction=(
            "本轮必须明确回应上一轮，不要代写其他 Agent 的完整发言。"
            "你的角色/立场：反方，主张 AI 快速发展弊大于利。"
        ),
        depends_on=("turn-1",),
        task_type="dialogue_turn",
    )

    validation = validate_task_output(
        task,
        _attempt(
            "针对上一轮正方关于效率和医疗收益的说法，我认为问题在速度和分配。"
            "技术迭代远超制度、监管和再培训能力时，普通劳动者会先承受就业替代、"
            "隐私滥用、数据垄断和算力集中带来的结构性撕裂。生成式 AI 的能耗、"
            "碳排放和信息污染也会被全社会承担，而头部平台拿走主要收益。"
        ),
    )

    assert validation.passed
    assert "结构性撕裂" in validation.summary_text


def test_dialogue_turn_accepts_substantive_reply_with_agent_mention() -> None:
    task = SubTask(
        task_id="turn-2",
        agent_id="opencode-helper",
        title="第 2 轮发言：反方",
        instruction=(
            "本轮必须明确回应上一轮，不要代写其他 Agent 的完整发言。"
            "你的角色/立场：反方，主张 AI 快速发展弊大于利。"
        ),
        depends_on=("turn-1",),
        task_type="dialogue_turn",
    )

    validation = validate_task_output(
        task,
        _attempt(
            "@claude-code 你拿医疗说事我承认有亮点，但镜头得拉全。"
            "AI 诊断在真实医院里会遇到数据偏移、偏见和可解释性问题，"
            "如果错误决策被规模化部署，伤害也会被放大。你说技术普惠，"
            "现实中算力和数据集中在少数平台，普通人更可能承担失业、"
            "隐私和安全风险。因此我反驳上一轮：快速发展如果缺少治理，"
            "社会代价会超过局部效率收益。"
        ),
    )

    assert validation.passed
    assert "@claude-code" in validation.summary_text


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


def test_analysis_contract_rejects_prompt_echo_without_contribution() -> None:
    task = _task(
        title="分析渠道数据",
        instruction=(
            "@orchestrator 不需要生成文件，请让两个智能体分析这组数据："
            "渠道 A 转化率 12%、渠道 B 转化率 7%、渠道 C 转化率 15%，预算分别为"
            " 30/20/10 万。请直接在群聊里给出结论、依据和下一步建议。"
        ),
    )

    validation = validate_task_output(
        task,
        _attempt(
            "@claude-code @opencode-helper 请你们两位分别分析以下数据，直接在"
            "群聊中给出结论、依据和下一步建议：渠道 A 转化率 12%、渠道 B "
            "转化率 7%、渠道 C 转化率 15%，预算分别为 30/20/10 万。"
            "不生成文件。"
        ),
    )

    assert not validation.passed
    assert "复述任务" in validation.reason


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


def test_generic_roundtable_conversation_accepts_substantive_topic_output() -> None:
    task = _task(
        task_type="conversation",
        title="第一位成员发言：中小企业是否应该接入 AI 客服",
        instruction=(
            "角色：第一位讨论成员，给出建设性观点、理由和具体建议。"
            "主题：中小企业是否应该接入 AI 客服。"
        ),
    )

    validation = validate_task_output(
        task,
        _attempt(
            "核心观点：中小企业可以先在低风险客服场景接入 AI 客服。"
            "主要理由是常见问题自动回复能降低等待时间，也能让人工客服集中处理"
            "复杂投诉。风险在于错误答复和隐私合规，因此建议先限定知识库、"
            "保留人工转接，并按月复盘误答率。"
        ),
    )

    assert validation.passed
    assert "核心观点" in validation.summary_text


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
