import { useChatStore } from './chatStore';
import { mockConversations, mockMessages } from '@/lib/mockData';

function resetChatStore() {
  useChatStore.setState({
    conversations: [...mockConversations],
    messagesByConversation: structuredClone(mockMessages),
    selectedConversationId: mockConversations[0]?.id ?? '',
    search: '',
    highlightedMessageId: null,
  });
}

describe('chatStore', () => {
  beforeEach(() => {
    resetChatStore();
  });

  it('creates a conversation and initializes an empty message list', () => {
    const conversation = useChatStore.getState().createConversation({
      title: '测试会话',
      mode: 'group',
      agentIds: ['orchestrator', 'codex-helper'],
    });

    const state = useChatStore.getState();
    expect(state.conversations[0]).toMatchObject({
      id: conversation.id,
      title: '测试会话',
      mode: 'group',
      agent_ids: ['orchestrator', 'codex-helper'],
    });
    expect(state.messagesByConversation[conversation.id]).toEqual([]);
    expect(state.selectedConversationId).toBe(conversation.id);
  });

  it('routes group messages to mentioned agents', () => {
    const result = useChatStore
      .getState()
      .createPendingExchange('conv-demo-flow', '@codex-helper 帮我实现测试');

    expect(result?.agentMessageId).toContain('msg-codex-helper-');

    const messages = useChatStore.getState().messagesByConversation['conv-demo-flow'];
    expect(messages.at(-2)?.role).toBe('user');
    expect(messages.at(-1)).toMatchObject({
      id: result?.agentMessageId,
      role: 'agent',
      agent_id: 'codex-helper',
      status: 'streaming',
    });
  });

  it('routes group messages to orchestrator when no agent is mentioned', () => {
    const result = useChatStore
      .getState()
      .createPendingExchange('conv-demo-flow', '请拆解这个任务');

    expect(result?.agentMessageId).toContain('msg-orchestrator-');
  });

  it('applies stream events to text, code, task card and agent switch blocks', () => {
    const result = useChatStore
      .getState()
      .createPendingExchange('conv-demo-flow', '@orchestrator 做一次协作演示');
    const messageId = result?.agentMessageId;
    expect(messageId).toBeTruthy();

    const store = useChatStore.getState();
    store.applyStreamEvent(messageId!, { event: 'start', data: {} });
    store.applyStreamEvent(messageId!, {
      event: 'block_start',
      data: {
        block_index: 0,
        block_type: 'task_card',
        metadata: {
          title: '测试任务',
          tasks: [
            { id: 'plan', agent_id: 'orchestrator', title: '规划', status: 'running' },
            { id: 'code', agent_id: 'codex-helper', title: '实现', status: 'pending' },
          ],
        },
      },
    });
    store.applyStreamEvent(messageId!, {
      event: 'block_start',
      data: { block_index: 1, block_type: 'text' },
    });
    store.applyStreamEvent(messageId!, {
      event: 'delta',
      data: { block_index: 1, text_delta: 'hello' },
    });
    store.applyStreamEvent(messageId!, {
      event: 'tool_call',
      data: {
        call_id: 'call-write',
        tool_name: 'write_file',
        tool_arguments: { path: 'public/demo.html' },
      },
    });
    store.applyStreamEvent(messageId!, {
      event: 'tool_result',
      data: {
        call_id: 'call-write',
        tool_status: 'ok',
        tool_output: 'wrote file',
      },
    });
    store.applyStreamEvent(messageId!, {
      event: 'agent_switch',
      data: { from_agent: 'orchestrator', to_agent: 'codex-helper', task: '实现代码' },
    });
    store.applyStreamEvent(messageId!, {
      event: 'block_start',
      data: { block_index: 4, block_type: 'code', metadata: { language: 'tsx' } },
    });
    store.applyStreamEvent(messageId!, {
      event: 'delta',
      data: { block_index: 4, code_delta: 'export {}' },
    });
    store.applyStreamEvent(messageId!, { event: 'done', data: { total_blocks: 4 } });

    const message = useChatStore
      .getState()
      .messagesByConversation['conv-demo-flow']
      .find((item) => item.id === messageId);

    expect(message?.status).toBe('done');
    expect(message?.content[0]).toMatchObject({ type: 'task_card', title: '测试任务' });
    expect(message?.content[1]).toMatchObject({ type: 'text', text: 'hello' });
    expect(message?.content[2]).toMatchObject({
      type: 'tool_call',
      call_id: 'call-write',
      status: 'ok',
      output_preview: 'wrote file',
    });
    expect(message?.content[3]).toMatchObject({ type: 'agent_switch', to_agent: 'codex-helper' });
    expect(message?.content[4]).toMatchObject({ type: 'code', language: 'tsx', code: 'export {}' });
  });

  it('marks stream errors and supports retry reset', () => {
    const result = useChatStore
      .getState()
      .createPendingExchange('conv-react-todo', '写一个 Todo');
    const messageId = result?.agentMessageId;
    expect(messageId).toBeTruthy();

    useChatStore.getState().applyStreamEvent(messageId!, {
      event: 'error',
      data: { error: 'network failed' },
    });

    let message = useChatStore
      .getState()
      .messagesByConversation['conv-react-todo']
      .find((item) => item.id === messageId);
    expect(message?.status).toBe('error');
    expect(message?.content[0]).toMatchObject({ type: 'text' });

    useChatStore.getState().resetMessageForRetry(messageId!);
    message = useChatStore
      .getState()
      .messagesByConversation['conv-react-todo']
      .find((item) => item.id === messageId);
    expect(message).toMatchObject({
      status: 'streaming',
      content: [{ type: 'text', text: '' }],
    });
  });

  it('toggles message pin state and highlighted message id', () => {
    const messageId = 'msg-demo-1';

    useChatStore.getState().toggleMessagePin(messageId);
    useChatStore.getState().setHighlightedMessageId(messageId);

    const message = useChatStore
      .getState()
      .messagesByConversation['conv-demo-flow']
      .find((item) => item.id === messageId);

    expect(message?.is_pinned).toBe(false);
    expect(useChatStore.getState().highlightedMessageId).toBe(messageId);
  });

  it('toggles conversation pin state', () => {
    useChatStore.getState().toggleConversationPin('conv-product-copy');

    const pinned = useChatStore
      .getState()
      .conversations.find((conversation) => conversation.id === 'conv-product-copy');

    expect(pinned?.is_pinned).toBe(true);
  });

  it('archives a conversation and moves selection to a visible conversation', () => {
    useChatStore.getState().setSelectedConversationId('conv-demo-flow');
    useChatStore.getState().toggleConversationArchive('conv-demo-flow');

    const state = useChatStore.getState();
    const archived = state.conversations.find((conversation) => conversation.id === 'conv-demo-flow');

    expect(archived?.is_archived).toBe(true);
    expect(state.selectedConversationId).not.toBe('conv-demo-flow');
  });

  it('upserts remote conversation updates and moves selection away from archived conversations', () => {
    useChatStore.setState({
      conversations: [],
      messagesByConversation: {},
      selectedConversationId: 'remote-conv',
    });

    useChatStore.getState().updateConversationLocal({
      id: 'remote-conv',
      title: '远端归档会话',
      mode: 'single',
      agent_ids: ['claude-code'],
      is_pinned: false,
      is_archived: true,
      last_message_at: '2026-05-29T12:00:00.000Z',
      last_message_preview: null,
      created_at: '2026-05-29T12:00:00.000Z',
    });

    const state = useChatStore.getState();
    expect(state.conversations).toHaveLength(1);
    expect(state.conversations[0]).toMatchObject({
      id: 'remote-conv',
      is_archived: true,
    });
    expect(state.selectedConversationId).toBe('');
  });
});
