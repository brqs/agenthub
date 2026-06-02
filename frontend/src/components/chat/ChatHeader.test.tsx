import { fireEvent, render, screen } from '@testing-library/react';
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

  it('opens mobile conversation and workspace surfaces', () => {
    const onOpenConversationList = vi.fn();
    const onOpenWorkspace = vi.fn();
    render(
      <ChatHeader
        conversation={conversation}
        agents={mockAgents}
        onOpenConversationList={onOpenConversationList}
        onOpenWorkspace={onOpenWorkspace}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '打开会话列表' }));
    fireEvent.click(screen.getByRole('button', { name: '打开工作台' }));

    expect(onOpenConversationList).toHaveBeenCalledOnce();
    expect(onOpenWorkspace).toHaveBeenCalledOnce();
  });

  it('opens workspace from the mobile more menu', () => {
    const onOpenWorkspace = vi.fn();
    render(
      <ChatHeader conversation={conversation} agents={mockAgents} onOpenWorkspace={onOpenWorkspace} />,
    );

    fireEvent.click(screen.getByRole('button', { name: '更多操作' }));
    expect(screen.getByText('会话 Agent')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '从更多菜单打开工作台' }));

    expect(onOpenWorkspace).toHaveBeenCalledOnce();
  });
});
