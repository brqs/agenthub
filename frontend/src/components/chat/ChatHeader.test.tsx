import { render, screen } from '@testing-library/react';
import { ChatHeader } from './ChatHeader';
import { mockAgents, type DemoConversation } from '@/lib/mockData';

const conversation: DemoConversation = {
  id: 'conv-header',
  title: '真实 Agent 会话',
  mode: 'group',
  agent_ids: ['orchestrator', 'claude-code'],
  is_pinned: false,
  is_archived: false,
  last_message_at: new Date().toISOString(),
  created_at: new Date().toISOString(),
};

describe('ChatHeader', () => {
  it('resolves header agents from injected agent data', () => {
    render(<ChatHeader conversation={conversation} agents={mockAgents} />);

    expect(screen.getByText('真实 Agent 会话')).toBeInTheDocument();
    expect(screen.getByText(/2 Agents · Orchestrator, Claude Code/)).toBeInTheDocument();
  });

  it('falls back to conversation agent ids without mock lookup', () => {
    render(<ChatHeader conversation={conversation} agents={[]} />);

    expect(screen.getByText(/2 Agents · orchestrator, claude-code/)).toBeInTheDocument();
  });
});
