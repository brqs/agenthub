import type { AgentSwitchBlock, DemoConversation, DemoMessage, TaskCardBlock } from '@/lib/mockData';
import { getAgent } from '@/lib/mockData';

export interface OrchestratorSnapshot {
  modeLabel: string;
  stage: 'Single Agent' | 'Planning' | 'Generating' | 'Done';
  currentAgentId: string;
  currentAgentName: string;
  switchLabel: string | null;
  totalTasks: number;
  doneTasks: number;
  runningTaskTitle: string | null;
}

export function findLatestTaskCard(messages: DemoMessage[]): TaskCardBlock | null {
  for (const message of [...messages].reverse()) {
    const taskCard = [...message.content].reverse().find((block) => block.type === 'task_card');
    if (taskCard?.type === 'task_card') return taskCard;
  }
  return null;
}

function findLatestAgentSwitch(messages: DemoMessage[]): AgentSwitchBlock | null {
  for (const message of [...messages].reverse()) {
    const agentSwitch = [...message.content].reverse().find((block) => block.type === 'agent_switch');
    if (agentSwitch?.type === 'agent_switch') return agentSwitch;
  }
  return null;
}

export function getOrchestratorSnapshot(
  conversation: DemoConversation,
  messages: DemoMessage[],
): OrchestratorSnapshot {
  if (conversation.mode !== 'group') {
    const agent = getAgent(conversation.agent_ids[0]);
    return {
      modeLabel: '单 Agent 模式',
      stage: 'Single Agent',
      currentAgentId: agent?.id ?? 'agent',
      currentAgentName: agent?.name ?? 'Agent',
      switchLabel: null,
      totalTasks: 0,
      doneTasks: 0,
      runningTaskTitle: null,
    };
  }

  const taskCard = findLatestTaskCard(messages);
  const agentSwitch = findLatestAgentSwitch(messages);
  const runningTask = taskCard?.tasks.find((task) => task.status === 'running') ?? null;
  const doneTasks = taskCard?.tasks.filter((task) => task.status === 'done').length ?? 0;
  const totalTasks = taskCard?.tasks.length ?? 0;
  const activeAgentId = runningTask?.agent_id ?? agentSwitch?.to_agent ?? 'orchestrator';
  const fromAgent = getAgent(agentSwitch?.from_agent);
  const toAgent = getAgent(agentSwitch?.to_agent);
  const allDone = totalTasks > 0 && doneTasks === totalTasks;

  return {
    modeLabel: 'Orchestrated 群聊',
    stage: allDone ? 'Done' : runningTask ? 'Generating' : 'Planning',
    currentAgentId: activeAgentId,
    currentAgentName: getAgent(activeAgentId)?.name ?? activeAgentId,
    switchLabel: agentSwitch
      ? `${fromAgent?.name ?? agentSwitch.from_agent} -> ${toAgent?.name ?? agentSwitch.to_agent}`
      : null,
    totalTasks,
    doneTasks,
    runningTaskTitle: runningTask?.title ?? null,
  };
}
