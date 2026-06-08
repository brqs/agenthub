import type { AgentSwitchBlock, DemoConversation, DemoMessage, TaskCardBlock } from '@/lib/mockData';
import type { Agent } from '@/lib/types';

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
  agents: Agent[],
): OrchestratorSnapshot {
  if (conversation.mode !== 'group') {
    const agent = agents.find((item) => item.id === conversation.agent_ids[0]);
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
  const activeAgentId = runningTask ? taskAgentId(runningTask) : (agentSwitch?.to_agent ?? 'orchestrator');
  const fromAgent = agents.find((item) => item.id === agentSwitch?.from_agent);
  const toAgent = agents.find((item) => item.id === agentSwitch?.to_agent);
  const allDone = totalTasks > 0 && doneTasks === totalTasks;

  return {
    modeLabel: 'Orchestrated 群聊',
    stage: allDone ? 'Done' : runningTask ? 'Generating' : 'Planning',
    currentAgentId: activeAgentId,
    currentAgentName: agents.find((item) => item.id === activeAgentId)?.name ?? activeAgentId,
    switchLabel: agentSwitch
      ? `${fromAgent?.name ?? agentSwitch.from_agent} -> ${toAgent?.name ?? agentSwitch.to_agent}`
      : null,
    totalTasks,
    doneTasks,
    runningTaskTitle: runningTask?.title ?? null,
  };
}

function taskAgentId(task: TaskCardBlock['tasks'][number]): string {
  return task.final_agent_id ?? task.current_agent_id ?? task.agent_id;
}
