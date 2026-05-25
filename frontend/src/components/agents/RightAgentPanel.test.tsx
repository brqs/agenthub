import { render, screen } from '@testing-library/react';
import { RightAgentPanel } from './RightAgentPanel';
import type { DemoConversation, DemoMessage } from '@/lib/mockData';

const conversation: DemoConversation = {
  id: 'conv-panel',
  title: '右栏状态测试',
  mode: 'group',
  agent_ids: ['orchestrator', 'web-designer', 'codex-helper', 'claude-code'],
  is_pinned: false,
  is_archived: false,
  last_message_at: new Date().toISOString(),
  created_at: new Date().toISOString(),
};

const messages: DemoMessage[] = [
  {
    id: 'msg-panel',
    conversation_id: conversation.id,
    role: 'agent',
    agent_id: 'orchestrator',
    reply_to_id: null,
    status: 'done',
    is_pinned: true,
    created_at: new Date().toISOString(),
    content: [
      {
        type: 'task_card',
        title: '右栏任务流',
        tasks: [
          { id: 'task-1', agent_id: 'orchestrator', title: '拆解任务', status: 'done' },
          { id: 'task-2', agent_id: 'web-designer', title: '优化层级', status: 'done' },
          { id: 'task-3', agent_id: 'codex-helper', title: '输出实现', status: 'running' },
          { id: 'task-4', agent_id: 'claude-code', title: '复核风险', status: 'pending' },
        ],
      },
    ],
  },
];

describe('RightAgentPanel', () => {
  it('shows active, done, and idle agent states derived from tasks', () => {
    render(<RightAgentPanel conversation={conversation} messages={messages} />);

    expect(screen.getAllByText('Codex Helper').length).toBeGreaterThan(0);
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getAllByText('Done')).toHaveLength(2);
    expect(screen.getByText('Idle')).toBeInTheDocument();
  });
});
