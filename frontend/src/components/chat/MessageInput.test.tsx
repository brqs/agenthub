import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MessageInput } from './MessageInput';
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
  it('sends trimmed text by click', async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<MessageInput conversation={singleConversation} onSend={onSend} />);

    const input = screen.getByPlaceholderText('发消息到 单聊测试');
    fireEvent.change(input, {
      target: { value: '  hello  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith('hello');
      expect(input).toHaveValue('');
    });
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

  it('keeps text and shows an error when sending fails', async () => {
    const onSend = vi.fn().mockRejectedValue(new Error('上一条回复仍未结束，请稍后再发。'));
    render(<MessageInput conversation={singleConversation} onSend={onSend} />);
    const input = screen.getByPlaceholderText('发消息到 单聊测试');

    fireEvent.change(input, { target: { value: '你好' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));

    await waitFor(() => {
      expect(screen.getByText('上一条回复仍未结束，请稍后再发。')).toBeInTheDocument();
    });
    expect(input).toHaveValue('你好');
  });

  it('sends with Enter and keeps Shift+Enter for newline', async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<MessageInput conversation={singleConversation} onSend={onSend} />);
    const input = screen.getByPlaceholderText('发消息到 单聊测试');

    fireEvent.change(input, { target: { value: 'hello' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();

    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith('hello');
      expect(input).toHaveValue('');
    });
  });

  it('disables input while sending', () => {
    render(<MessageInput conversation={singleConversation} onSend={vi.fn()} isSending />);

    expect(screen.getByPlaceholderText('发消息到 单聊测试')).toBeDisabled();
  });

  it('disables input and sending while offline', () => {
    const onSend = vi.fn();
    render(<MessageInput conversation={singleConversation} onSend={onSend} isOffline />);

    const input = screen.getByPlaceholderText('当前离线，恢复网络后可继续发送');
    expect(input).toBeDisabled();
    expect(screen.getByText('当前离线，恢复网络后可继续发送')).toBeInTheDocument();
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(onSend).not.toHaveBeenCalled();
  });

  it('shows mention picker in group conversations and inserts selected agent', () => {
    render(<MessageInput conversation={groupConversation} agents={mockAgents} onSend={vi.fn()} />);
    const input = screen.getByPlaceholderText('发消息到 群聊测试');

    fireEvent.change(input, { target: { value: '@' } });
    fireEvent.click(screen.getByText('Codex Helper'));

    expect(input).toHaveValue('@codex-helper ');
  });

  it('shows slash command suggestions and inserts selected command', () => {
    render(<MessageInput conversation={groupConversation} agents={mockAgents} onSend={vi.fn()} />);
    const input = screen.getByPlaceholderText('发消息到 群聊测试');

    fireEvent.change(input, { target: { value: '/gr' } });
    fireEvent.click(screen.getByText('/grill-me'));

    expect(input).toHaveValue('/grill-me ');
  });

  it('fills input from clarification card answer chips', () => {
    const onSend = vi.fn();
    render(<MessageInput conversation={groupConversation} agents={mockAgents} onSend={onSend} />);
    const input = screen.getByPlaceholderText('发消息到 群聊测试');

    act(() => {
      window.dispatchEvent(
        new CustomEvent('agenthub:fill-message-input', {
          detail: { text: '使用推荐答案' },
        }),
      );
    });

    expect(input).toHaveValue('使用推荐答案');
    expect(onSend).not.toHaveBeenCalled();
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
});
