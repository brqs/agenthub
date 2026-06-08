import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MessageInput } from './MessageInput';
import { mockAgents, type DemoConversation } from '@/lib/mockData';
import { uploadFile } from '@/lib/adapters/uploads';

vi.mock('@/lib/adapters/uploads', () => ({
  uploadFile: vi.fn(),
}));

const uploadFileMock = vi.mocked(uploadFile);

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
  beforeEach(() => {
    uploadFileMock.mockReset();
  });

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

  it('shows a stop button while streaming and keeps the textarea editable', async () => {
    const onSend = vi.fn();
    const onInterrupt = vi.fn().mockResolvedValue(undefined);
    render(
      <MessageInput
        conversation={singleConversation}
        onSend={onSend}
        isStreaming
        onInterrupt={onInterrupt}
      />,
    );
    const input = screen.getByPlaceholderText('发消息到 单聊测试');

    expect(input).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '停止回复' }));

    await waitFor(() => {
      expect(onInterrupt).toHaveBeenCalledTimes(1);
    });
    expect(onSend).not.toHaveBeenCalled();
  });

  it('queues text with Enter while streaming', async () => {
    const onSend = vi.fn();
    const onQueue = vi.fn().mockResolvedValue(undefined);
    const onInterrupt = vi.fn().mockResolvedValue(undefined);
    render(
      <MessageInput
        conversation={singleConversation}
        onSend={onSend}
        onQueue={onQueue}
        isStreaming
        onInterrupt={onInterrupt}
      />,
    );
    const input = screen.getByPlaceholderText('发消息到 单聊测试');

    fireEvent.change(input, { target: { value: '  补充要求  ' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => {
      expect(onQueue).toHaveBeenCalledWith('补充要求');
      expect(input).toHaveValue('');
    });
    expect(onSend).not.toHaveBeenCalled();
    expect(onInterrupt).not.toHaveBeenCalled();
  });

  it('shows separate stop and queue actions while streaming with text', async () => {
    const onQueue = vi.fn().mockResolvedValue(undefined);
    const onInterrupt = vi.fn().mockResolvedValue(undefined);
    render(
      <MessageInput
        conversation={singleConversation}
        onSend={vi.fn()}
        onQueue={onQueue}
        isStreaming
        onInterrupt={onInterrupt}
      />,
    );
    const input = screen.getByPlaceholderText('发消息到 单聊测试');

    fireEvent.change(input, { target: { value: '下一步' } });
    fireEvent.click(screen.getByRole('button', { name: '发送到队列' }));

    await waitFor(() => {
      expect(onQueue).toHaveBeenCalledWith('下一步');
    });
    expect(onInterrupt).not.toHaveBeenCalled();
  });

  it('runs explicit active-turn controls from the streaming action menu', async () => {
    const onQueue = vi.fn().mockResolvedValue(undefined);
    const onGuidance = vi.fn().mockResolvedValue(undefined);
    const onSideChat = vi.fn().mockResolvedValue(undefined);
    const onStopAndRun = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <MessageInput
        conversation={singleConversation}
        onSend={vi.fn()}
        onQueue={onQueue}
        onGuidance={onGuidance}
        onSideChat={onSideChat}
        onStopAndRun={onStopAndRun}
        isStreaming
      />,
    );
    const input = screen.getByRole('textbox');

    fireEvent.change(input, { target: { value: 'make it darker' } });
    fireEvent.click(screen.getByRole('button', { name: 'More active turn actions' }));
    fireEvent.click(screen.getByRole('button', { name: 'Guide current reply' }));

    await waitFor(() => {
      expect(onGuidance).toHaveBeenCalledWith('make it darker');
      expect(input).toHaveValue('');
    });

    rerender(
      <MessageInput
        conversation={singleConversation}
        onSend={vi.fn()}
        onQueue={onQueue}
        onGuidance={onGuidance}
        onSideChat={onSideChat}
        onStopAndRun={onStopAndRun}
        isStreaming
      />,
    );
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'what is happening?' } });
    fireEvent.click(screen.getByRole('button', { name: 'More active turn actions' }));
    fireEvent.click(screen.getByRole('button', { name: 'Ask side question' }));
    await waitFor(() => {
      expect(onSideChat).toHaveBeenCalledWith('what is happening?');
    });

    rerender(
      <MessageInput
        conversation={singleConversation}
        onSend={vi.fn()}
        onQueue={onQueue}
        onGuidance={onGuidance}
        onSideChat={onSideChat}
        onStopAndRun={onStopAndRun}
        isStreaming
      />,
    );
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'run this now' } });
    fireEvent.click(screen.getByRole('button', { name: 'More active turn actions' }));
    fireEvent.click(screen.getByRole('button', { name: 'Stop and run draft' }));
    await waitFor(() => {
      expect(onStopAndRun).toHaveBeenCalledWith('run this now');
    });

    expect(onQueue).not.toHaveBeenCalled();
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

  it('uploads selected files and sends attachment ids with the message', async () => {
    uploadFileMock.mockResolvedValue({
      id: 'upload-1',
      filename: 'mockup.png',
      content_type: 'image/png',
      detected_content_type: 'image/png',
      size_bytes: 4,
      sha256: 'hash',
      purpose: 'message_attachment',
      status: 'ready',
      safety_status: 'passed',
      preview: { kind: 'image', thumbnail_url: '/thumb.png' },
    });
    const onSend = vi.fn().mockResolvedValue(undefined);
    const { container } = render(
      <MessageInput conversation={singleConversation} onSend={onSend} />,
    );
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const input = screen.getByPlaceholderText('发消息到 单聊测试');

    fireEvent.change(fileInput, {
      target: {
        files: [new File(['demo'], 'mockup.png', { type: 'image/png' })],
      },
    });

    expect(await screen.findByText('mockup.png')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('已就绪')).toBeInTheDocument());

    fireEvent.change(input, { target: { value: '参考这个图' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledWith('参考这个图', ['upload-1']);
    });
    expect(screen.queryByText('mockup.png')).not.toBeInTheDocument();
  });

  it('keeps text and blocks send while an attachment upload has failed', async () => {
    uploadFileMock.mockRejectedValue(new Error('上传失败'));
    const onSend = vi.fn().mockResolvedValue(undefined);
    const { container } = render(
      <MessageInput conversation={singleConversation} onSend={onSend} />,
    );
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const input = screen.getByPlaceholderText('发消息到 单聊测试');

    fireEvent.change(fileInput, {
      target: {
        files: [new File(['bad'], 'bad.zip', { type: 'application/zip' })],
      },
    });
    fireEvent.change(input, { target: { value: '带附件发送' } });

    expect(await screen.findByText('上传失败')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled();
    expect(onSend).not.toHaveBeenCalled();
    expect(input).toHaveValue('带附件发送');
  });

  it('limits attachments to ten files before upload', async () => {
    uploadFileMock.mockImplementation(async ({ filename }) => ({
      id: `upload-${filename}`,
      filename,
      content_type: 'text/plain',
      detected_content_type: 'text/plain',
      size_bytes: 4,
      sha256: 'hash',
      purpose: 'message_attachment',
      status: 'ready',
      safety_status: 'passed',
      preview: { kind: 'text', text_preview: filename },
    }));
    const { container } = render(
      <MessageInput conversation={singleConversation} onSend={vi.fn()} />,
    );
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    fireEvent.change(fileInput, {
      target: {
        files: Array.from({ length: 11 }, (_, index) =>
          new File(['demo'], `file-${index}.txt`, { type: 'text/plain' }),
        ),
      },
    });

    expect(await screen.findByText(/已忽略多余文件/)).toBeInTheDocument();
    await waitFor(() => expect(uploadFileMock).toHaveBeenCalledTimes(10));
    expect(screen.queryByText('file-10.txt')).not.toBeInTheDocument();
  });

  it('does not open uploads while offline', () => {
    const { container } = render(
      <MessageInput conversation={singleConversation} onSend={vi.fn()} isOffline />,
    );
    const addButton = screen.getByRole('button', { name: '添加附件' });
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    expect(addButton).toBeDisabled();
    fireEvent.change(fileInput, {
      target: {
        files: [new File(['demo'], 'offline.txt', { type: 'text/plain' })],
      },
    });
    expect(screen.getByText(/恢复网络后再上传附件/)).toBeInTheDocument();
    expect(uploadFileMock).not.toHaveBeenCalled();
  });
});
