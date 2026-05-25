import { render, screen } from '@testing-library/react';
import { OrchestratorStatusCard } from './OrchestratorStatusCard';
import { getOrchestratorSnapshot } from './orchestratorStatus';
import type { DemoConversation, DemoMessage } from '@/lib/mockData';

const groupConversation: DemoConversation = {
  id: 'conv-status',
  title: '状态测试',
  mode: 'group',
  agent_ids: ['orchestrator', 'web-designer', 'codex-helper'],
  is_pinned: false,
  is_archived: false,
  last_message_at: new Date().toISOString(),
  created_at: new Date().toISOString(),
};

const messages: DemoMessage[] = [
  {
    id: 'msg-status',
    conversation_id: groupConversation.id,
    role: 'agent',
    agent_id: 'orchestrator',
    reply_to_id: null,
    status: 'done',
    is_pinned: false,
    created_at: new Date().toISOString(),
    content: [
      {
        type: 'task_card',
        title: '任务流',
        tasks: [
          { id: 'task-1', agent_id: 'orchestrator', title: '拆解任务', status: 'done' },
          { id: 'task-2', agent_id: 'codex-helper', title: '输出实现', status: 'running' },
        ],
      },
      {
        type: 'agent_switch',
        from_agent: 'orchestrator',
        to_agent: 'codex-helper',
        task: '输出实现',
      },
    ],
  },
];

describe('OrchestratorStatusCard', () => {
  it('derives collaboration status from task card and agent switch blocks', () => {
    const snapshot = getOrchestratorSnapshot(groupConversation, messages);

    expect(snapshot.stage).toBe('Generating');
    expect(snapshot.currentAgentName).toBe('Codex Helper');
    expect(snapshot.doneTasks).toBe(1);
    expect(snapshot.totalTasks).toBe(2);
  });

  it('renders progress and active task', () => {
    render(<OrchestratorStatusCard conversation={groupConversation} messages={messages} />);

    expect(screen.getByText('Orchestrated 群聊')).toBeInTheDocument();
    expect(screen.getByText('1 / 2')).toBeInTheDocument();
    expect(screen.getByText('输出实现')).toBeInTheDocument();
  });
});
