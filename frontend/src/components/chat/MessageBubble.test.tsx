import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MessageBubble, visibleMessageBlocks } from './MessageBubble';
import type { DemoMessage } from '@/lib/mockData';
import type { Agent } from '@/lib/types';
import type { ReactElement } from 'react';

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

function renderWithQueryClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('MessageBubble', () => {
  it('filters legacy orchestrator trace text from completed messages', () => {
    const message: DemoMessage = {
      ...agentMessage,
      agent_id: 'orchestrator',
      content: [
        { type: 'task_card', title: 'Plan', tasks: [] },
        { type: 'text', text: 'ReAct step 1\nObservation: internal\nAction: finish' },
        { type: 'text', text: 'Execution summary\n\n- succeeded: @opencode-helper' },
        { type: 'text', text: 'Here is the direct answer.' },
      ],
    };

    expect(visibleMessageBlocks(message)).toEqual([
      { type: 'task_card', title: 'Plan', tasks: [] },
      { type: 'text', text: 'Here is the direct answer.' },
    ]);
  });

  it('filters legacy orchestrator trace text from failed messages', () => {
    const message: DemoMessage = {
      ...agentMessage,
      agent_id: 'orchestrator',
      status: 'error',
      content: [
        { type: 'task_card', title: 'Plan', tasks: [] },
        { type: 'text', text: 'Planned 1 sub-task(s) via LLM planner/config:\n1. @agent - Task' },
        { type: 'text', text: 'Execution summary\n\n- failed: @agent - Task' },
        { type: 'text', text: '调用失败：Agent 回复失败，请重试这条消息。' },
        { type: 'text', text: '调用失败：duplicate failure text' },
      ],
    };

    expect(visibleMessageBlocks(message)).toEqual([
      { type: 'task_card', title: 'Plan', tasks: [] },
      { type: 'text', text: '调用失败：Agent 回复失败，请重试这条消息。' },
    ]);
  });

  it('shows a fallback text block for legacy empty error messages', () => {
    const message: DemoMessage = {
      ...agentMessage,
      status: 'error',
      content: [],
    };

    expect(visibleMessageBlocks(message)).toEqual([
      { type: 'text', text: '调用失败：后端未返回错误详情，请重试。' },
    ]);
  });

  it('shows a neutral fallback block for empty interrupted messages', () => {
    const message: DemoMessage = {
      ...agentMessage,
      status: 'interrupted',
      content: [],
    };

    expect(visibleMessageBlocks(message)).toEqual([
      { type: 'text', text: '已打断本次回复，可以继续补充要求。' },
    ]);
  });

  it('renders interrupted messages without a retry action', () => {
    const onRetry = vi.fn();
    render(
      <MessageBubble
        message={{
          ...agentMessage,
          status: 'interrupted',
          content: [{ type: 'text', text: '已打断本次回复，可以继续补充要求。' }],
        }}
        agents={[codexAgent]}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText('已打断')).toBeInTheDocument();
    expect(screen.getByText('已打断本次回复，可以继续补充要求。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
  });

  it('renders queued user messages with edit and delete actions', async () => {
    const onUpdateQueuedMessage = vi.fn().mockResolvedValue(undefined);
    const onDeleteQueuedMessage = vi.fn().mockResolvedValue(undefined);
    render(
      <MessageBubble
        message={{
          id: 'msg-queued',
          conversation_id: 'conv-group',
          role: 'user',
          agent_id: null,
          reply_to_id: null,
          status: 'queued',
          is_pinned: false,
          created_at: new Date().toISOString(),
          content: [{ type: 'text', text: 'queued next' }],
        }}
        onUpdateQueuedMessage={onUpdateQueuedMessage}
        onDeleteQueuedMessage={onDeleteQueuedMessage}
      />,
    );

    expect(screen.getByText('Queued')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Edit queued message' }));
    fireEvent.change(screen.getByDisplayValue('queued next'), {
      target: { value: 'queued edited' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      expect(onUpdateQueuedMessage).toHaveBeenCalledWith('msg-queued', 'queued edited');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Delete queued message' }));
    await waitFor(() => {
      expect(onDeleteQueuedMessage).toHaveBeenCalledWith('msg-queued');
    });
  });

  it('renders a failure card for visible error text', () => {
    render(
      <MessageBubble
        message={{
          ...agentMessage,
          status: 'error',
          content: [{ type: 'text', text: 'failed: External runtime exceeded idle_timeout_seconds' }],
        }}
        agents={[codexAgent]}
      />,
    );

    expect(screen.getByText('调用失败')).toBeInTheDocument();
    expect(screen.getByText('failed: External runtime exceeded idle_timeout_seconds')).toBeInTheDocument();
  });

  it('shows an initial streaming state for an empty orchestrator message', () => {
    renderWithQueryClient(
      <MessageBubble
        message={{
          ...agentMessage,
          agent_id: 'orchestrator',
          status: 'streaming',
          content: [],
        }}
      />,
    );

    expect(screen.getByRole('status', { name: '正在分析请求...' })).toBeInTheDocument();
  });

  it('shows an immediate stopping state while an empty streaming message is interrupting', () => {
    renderWithQueryClient(
      <MessageBubble
        message={{
          ...agentMessage,
          agent_id: 'orchestrator',
          status: 'streaming',
          content: [],
        }}
        isInterrupting
      />,
    );

    expect(screen.getByText('正在停止')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: '正在停止本次回复...' })).toBeInTheDocument();
    expect(screen.queryByText('正在分析请求...')).not.toBeInTheDocument();
  });

  it('shows a pending preparation state for an empty orchestrator message', () => {
    renderWithQueryClient(
      <MessageBubble
        message={{
          ...agentMessage,
          agent_id: 'orchestrator',
          status: 'pending',
          content: [],
        }}
      />,
    );

    expect(screen.getByText('正在准备')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: '正在分析请求...' })).toBeInTheDocument();
  });

  it('shows an initial streaming state for an empty agent message', () => {
    render(
      <MessageBubble
        message={{
          ...agentMessage,
          status: 'streaming',
          content: [],
        }}
        agents={[codexAgent]}
      />,
    );

    expect(screen.getByRole('status', { name: '正在组织回复...' })).toBeInTheDocument();
  });

  it('shows an initial pending state for an empty agent message', () => {
    render(
      <MessageBubble
        message={{
          ...agentMessage,
          status: 'pending',
          content: [],
        }}
        agents={[codexAgent]}
      />,
    );

    expect(screen.getByText('正在准备')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: '正在组织回复...' })).toBeInTheDocument();
  });

  it('renders real streaming content instead of the initial empty state', () => {
    render(
      <MessageBubble
        message={{
          ...agentMessage,
          status: 'streaming',
          content: [{ type: 'text', text: '已经开始输出' }],
        }}
        agents={[codexAgent]}
      />,
    );

    expect(screen.getByText('已经开始输出')).toBeInTheDocument();
    expect(screen.queryByText('正在组织回复...')).not.toBeInTheDocument();
  });

  it('renders real pending content instead of the initial empty state', () => {
    render(
      <MessageBubble
        message={{
          ...agentMessage,
          status: 'pending',
          content: [{ type: 'text', text: '计划已经创建' }],
        }}
        agents={[codexAgent]}
      />,
    );

    expect(screen.getByText('计划已经创建')).toBeInTheDocument();
    expect(screen.queryByText('正在组织回复...')).not.toBeInTheDocument();
  });

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

  it('mentions an agent from the touch-friendly action', () => {
    const onMentionAgent = vi.fn();
    render(
      <MessageBubble message={agentMessage} agents={[codexAgent]} onMentionAgent={onMentionAgent} />,
    );

    fireEvent.click(screen.getByRole('button', { name: '@ Codex Helper' }));

    expect(onMentionAgent).toHaveBeenCalledWith(codexAgent);
  });
});
