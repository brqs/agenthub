import { fireEvent, render, screen } from '@testing-library/react';
import { MessageBubble } from './MessageBubble';
import type { DemoMessage } from '@/lib/mockData';
import type { Agent } from '@/lib/types';

const codexAgent: Agent = {
  id: 'codex-helper',
  name: 'Codex Helper',
  provider: 'codex',
  avatar_url: '',
  capabilities: [],
  config: {},
  is_builtin: false,
  created_at: new Date().toISOString(),
};

const agentMessage: DemoMessage = {
  id: 'msg-agent',
  conversation_id: 'conv-group',
  role: 'agent',
  agent_id: codexAgent.id,
  reply_to_id: null,
  status: 'done',
  is_pinned: false,
  created_at: new Date().toISOString(),
  content: [{ type: 'text', text: '我来处理。' }],
};

describe('MessageBubble', () => {
  it('opens an agent mention menu from the avatar context menu', () => {
    const onMentionAgent = vi.fn();
    render(
      <MessageBubble
        message={agentMessage}
        agents={[codexAgent]}
        onMentionAgent={onMentionAgent}
      />,
    );

    fireEvent.contextMenu(screen.getByTitle('右键 @Codex Helper'));
    fireEvent.click(screen.getByRole('menuitem', { name: '@ Codex Helper' }));

    expect(onMentionAgent).toHaveBeenCalledWith(codexAgent);
  });

  it('does not expose mention actions without a handler', () => {
    render(<MessageBubble message={agentMessage} agents={[codexAgent]} />);

    fireEvent.contextMenu(screen.getByText('Codex Helper'));

    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument();
  });
});
