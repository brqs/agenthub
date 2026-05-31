import { fireEvent, render, screen } from '@testing-library/react';
import { MessageInput } from './MessageInput';
import { DEMO_PROMPT } from './DemoPromptBar';
import { mockAgents, type DemoConversation } from '@/lib/mockData';

const singleConversation: DemoConversation = {
  id: 'conv-test-single',
  title: '单聊测试',
  mode: 'single',
  agent_ids: ['claude-code'],
  is_pinned: false,
  is_archived: false,
  last_message_at: new Date().toISOString(),
  created_at: new Date().toISOString(),
};

const groupConversation: DemoConversation = {
  ...singleConversation,
  id: 'conv-test-group',
  title: '群聊测试',
  mode: 'group',
  agent_ids: ['orchestrator', 'codex-helper'],
};

describe('MessageInput', () => {
  it('sends trimmed text by click', () => {
    const onSend = vi.fn();
    render(<MessageInput conversation={singleConversation} onSend={onSend} />);

    fireEvent.change(screen.getByPlaceholderText('发消息到 单聊测试'), {
      target: { value: '  hello  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));

    expect(onSend).toHaveBeenCalledWith('hello');
  });

  it('does not send blank text', () => {
    const onSend = vi.fn();
    render(<MessageInput conversation={singleConversation} onSend={onSend} />);

    fireEvent.change(screen.getByPlaceholderText('发消息到 单聊测试'), {
      target: { value: '   ' },
    });
    fireEvent.keyDown(screen.getByPlaceholderText('发消息到 单聊测试'), {
      key: 'Enter',
    });

    expect(onSend).not.toHaveBeenCalled();
  });

  it('sends with Enter and keeps Shift+Enter for newline', () => {
    const onSend = vi.fn();
    render(<MessageInput conversation={singleConversation} onSend={onSend} />);
    const input = screen.getByPlaceholderText('发消息到 单聊测试');

    fireEvent.change(input, { target: { value: 'hello' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();

    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSend).toHaveBeenCalledWith('hello');
  });

  it('disables input while sending', () => {
    render(<MessageInput conversation={singleConversation} onSend={vi.fn()} isSending />);

    expect(screen.getByPlaceholderText('发消息到 单聊测试')).toBeDisabled();
  });

  it('shows mention picker in group conversations and inserts selected agent', () => {
    render(<MessageInput conversation={groupConversation} agents={mockAgents} onSend={vi.fn()} />);
    const input = screen.getByPlaceholderText('发消息到 群聊测试');

    fireEvent.change(input, { target: { value: '@' } });
    fireEvent.click(screen.getByText('Codex Helper'));

    expect(input).toHaveValue('@codex-helper ');
  });

  it('inserts requested mentions from external agent actions', () => {
    const { rerender } = render(
      <MessageInput
        conversation={groupConversation}
        onSend={vi.fn()}
        mentionInsertRequest={{ agentId: 'codex-helper', requestId: 1 }}
      />,
    );
    const input = screen.getByPlaceholderText('发消息到 群聊测试');

    expect(input).toHaveValue('@codex-helper ');

    rerender(
      <MessageInput
        conversation={groupConversation}
        onSend={vi.fn()}
        mentionInsertRequest={{ agentId: 'orchestrator', requestId: 2 }}
      />,
    );

    expect(input).toHaveValue('@codex-helper @orchestrator ');
  });

  it('ignores external mention requests in single conversations', () => {
    render(
      <MessageInput
        conversation={singleConversation}
        onSend={vi.fn()}
        mentionInsertRequest={{ agentId: 'claude-code', requestId: 1 }}
      />,
    );

    expect(screen.getByPlaceholderText('发消息到 单聊测试')).toHaveValue('');
  });

  it('fills the demo prompt in group conversations', () => {
    render(<MessageInput conversation={groupConversation} onSend={vi.fn()} />);
    const input = screen.getByPlaceholderText('发消息到 群聊测试');

    fireEvent.click(screen.getByRole('button', { name: DEMO_PROMPT }));

    expect(input).toHaveValue(DEMO_PROMPT);
  });
});
