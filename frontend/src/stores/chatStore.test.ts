import { useChatStore } from './chatStore';
import { mockConversations, type DemoMessage } from '@/lib/mockData';
import type { Message } from '@/lib/types';

function resetChatStore() {
  useChatStore.getState().clearChat();
}

function addStreamingMessage(conversationId = 'conv-demo-flow'): string {
  const messageId = '00000000-0000-4000-8000-000000000099';
  const message: DemoMessage = {
    id: messageId,
    conversation_id: conversationId,
    role: 'agent',
    agent_id: 'orchestrator',
    reply_to_id: null,
    status: 'streaming',
    is_pinned: false,
    created_at: '2026-05-31T00:00:00.000Z',
    content: [],
  };
  useChatStore.setState((state) => ({
    messagesByConversation: {
      ...state.messagesByConversation,
      [conversationId]: [message],
    },
  }));
  return messageId;
}

function createMessage(overrides: Partial<Message> & Pick<Message, 'id' | 'role'>): Message {
  return {
    id: overrides.id,
    conversation_id: overrides.conversation_id ?? 'conv-demo-flow',
    role: overrides.role,
    agent_id: overrides.agent_id ?? null,
    reply_to_id: overrides.reply_to_id ?? null,
    status: overrides.status ?? 'done',
    is_pinned: overrides.is_pinned ?? false,
    created_at: overrides.created_at ?? '2026-05-31T00:00:00.000Z',
    content: overrides.content ?? [{ type: 'text', text: overrides.id }],
  };
}

describe('chatStore', () => {
  beforeEach(() => {
    resetChatStore();
  });

  it('starts empty until backend conversations are hydrated', () => {
    expect(useChatStore.getState()).toMatchObject({
      conversations: [],
      messagesByConversation: {},
      selectedConversationId: '',
    });
  });

  it('hydrates backend conversations and messages', () => {
    useChatStore.getState().hydrateConversations(structuredClone(mockConversations));
    const message: Message = {
      id: '00000000-0000-4000-8000-000000000001',
      conversation_id: 'conv-demo-flow',
      role: 'user',
      agent_id: null,
      reply_to_id: null,
      status: 'done',
      is_pinned: false,
      created_at: '2026-05-31T00:00:00.000Z',
      content: [{ type: 'text', text: 'hello' }],
    };
    useChatStore.getState().hydrateMessages('conv-demo-flow', [message]);

    expect(useChatStore.getState().selectedConversationId).toBe(mockConversations[0]?.id);
    expect(useChatStore.getState().messagesByConversation['conv-demo-flow']).toEqual([message]);
  });

  it('orders hydrated messages by display chronology and reply relationship', () => {
    const userOne = createMessage({
      id: '00000000-0000-4000-8000-000000000101',
      role: 'user',
      created_at: '2026-05-31T00:00:00.000Z',
    });
    const agentOne = createMessage({
      id: '00000000-0000-4000-8000-000000000102',
      role: 'agent',
      agent_id: 'claude-code',
      reply_to_id: userOne.id,
      created_at: '2026-05-31T00:00:00.000Z',
    });
    const userTwo = createMessage({
      id: '00000000-0000-4000-8000-000000000103',
      role: 'user',
      created_at: '2026-05-31T00:00:00.000Z',
    });
    const agentTwo = createMessage({
      id: '00000000-0000-4000-8000-000000000104',
      role: 'agent',
      agent_id: 'claude-code',
      reply_to_id: userTwo.id,
      created_at: '2026-05-31T00:00:00.000Z',
    });

    useChatStore
      .getState()
      .hydrateMessages('conv-demo-flow', [agentTwo, agentOne, userTwo, userOne]);

    expect(
      useChatStore.getState().messagesByConversation['conv-demo-flow'].map((message) => message.id),
    ).toEqual([userOne.id, agentOne.id, userTwo.id, agentTwo.id]);
  });

  it('keeps a replaced server message next to its parent user message', () => {
    const userMessage = createMessage({
      id: '00000000-0000-4000-8000-000000000201',
      role: 'user',
      created_at: '2026-05-31T00:00:00.000Z',
    });
    const pendingAgentMessage = createMessage({
      id: '00000000-0000-4000-8000-000000000202',
      role: 'agent',
      agent_id: 'claude-code',
      reply_to_id: userMessage.id,
      status: 'pending',
      created_at: '2026-05-31T00:00:00.000Z',
    });
    const nextUserMessage = createMessage({
      id: '00000000-0000-4000-8000-000000000203',
      role: 'user',
      created_at: '2026-05-31T00:00:00.000Z',
    });
    const completedAgentMessage = {
      ...pendingAgentMessage,
      status: 'done' as const,
      content: [{ type: 'text' as const, text: 'done' }],
    };

    useChatStore
      .getState()
      .hydrateMessages('conv-demo-flow', [userMessage, nextUserMessage, pendingAgentMessage]);
    useChatStore
      .getState()
      .replaceMessageLocal(pendingAgentMessage.id, completedAgentMessage);

    expect(
      useChatStore.getState().messagesByConversation['conv-demo-flow'].map((message) => message.id),
    ).toEqual([userMessage.id, pendingAgentMessage.id, nextUserMessage.id]);
  });

  it('applies stream events to text, code, task card and tool blocks', () => {
    const messageId = addStreamingMessage();
    const store = useChatStore.getState();
    store.applyStreamEvent(messageId, {
      event: 'block_start',
      data: {
        block_index: 0,
        block_type: 'task_card',
        metadata: {
          title: '测试任务',
          tasks: [{ id: 'plan', agent_id: 'orchestrator', title: '规划', status: 'running' }],
        },
      },
    });
    store.applyStreamEvent(messageId, {
      event: 'block_start',
      data: { block_index: 1, block_type: 'text' },
    });
    store.applyStreamEvent(messageId, {
      event: 'delta',
      data: { block_index: 1, text_delta: 'hello' },
    });
    store.applyStreamEvent(messageId, {
      event: 'tool_call',
      data: {
        call_id: 'call-write',
        tool_name: 'write_file',
        tool_arguments: { path: 'demo.html' },
      },
    });
    store.applyStreamEvent(messageId, {
      event: 'tool_result',
      data: { call_id: 'call-write', tool_status: 'ok', tool_output: 'wrote file' },
    });
    store.applyStreamEvent(messageId, { event: 'done', data: { total_blocks: 3 } });

    expect(useChatStore.getState().messagesByConversation['conv-demo-flow'][0]).toMatchObject({
      status: 'done',
      content: [
        { type: 'task_card', title: '测试任务' },
        { type: 'text', text: 'hello' },
        { type: 'tool_call', call_id: 'call-write', status: 'ok', output_preview: 'wrote file' },
      ],
    });
  });

  it('applies workflow stream events as workflow blocks', () => {
    const messageId = addStreamingMessage();
    const store = useChatStore.getState();
    store.applyStreamEvent(messageId, {
      event: 'block_start',
      data: {
        block_index: 0,
        block_type: 'workflow',
        agent_id: 'codex-helper',
        metadata: {
          format: 'yaml',
          validation_status: 'unknown',
          runtime_status: 'not_supported',
          dry_run_status: 'not_supported',
        },
      },
    });
    store.applyStreamEvent(messageId, {
      event: 'delta',
      data: {
        block_index: 0,
        agent_id: 'codex-helper',
        text_delta: "version: '1'\nname: Demo Flow\nnodes: []\nedges: []\n",
      },
    });

    expect(
      useChatStore.getState().messagesByConversation['conv-demo-flow'][0].content[0],
    ).toMatchObject({
      type: 'workflow',
      agent_id: 'codex-helper',
      format: 'yaml',
      raw_definition: "version: '1'\nname: Demo Flow\nnodes: []\nedges: []\n",
      runtime_status: 'not_supported',
    });
  });

  it('applies file stream events as rich file blocks', () => {
    const messageId = addStreamingMessage();
    const store = useChatStore.getState();
    store.applyStreamEvent(messageId, {
      event: 'block_start',
      data: {
        block_index: 0,
        block_type: 'file',
        agent_id: 'codex-helper',
        metadata: {
          path: 'docs/report.md',
          filename: 'report.md',
          url: '/api/v1/workspaces/conv-demo-flow/files/docs/report.md',
          size: 42,
          mime_type: 'text/markdown',
          artifact_kind: 'document',
          preview_text: '# Report',
          preview_truncated: false,
          metadata: { section_count: 1 },
        },
      },
    });
    store.applyStreamEvent(messageId, {
      event: 'delta',
      data: { block_index: 0, text_delta: 'ignored' },
    });

    expect(
      useChatStore.getState().messagesByConversation['conv-demo-flow'][0].content[0],
    ).toMatchObject({
      type: 'file',
      agent_id: 'codex-helper',
      path: 'docs/report.md',
      artifact_kind: 'document',
      filename: 'report.md',
      preview_text: '# Report',
    });
  });

  it('marks stream errors and supports retry reset', () => {
    const messageId = addStreamingMessage();
    useChatStore.getState().applyStreamEvent(messageId, {
      event: 'error',
      data: { error: 'network failed' },
    });
    useChatStore.getState().resetMessageForRetry(messageId);

    expect(useChatStore.getState().messagesByConversation['conv-demo-flow'][0]).toMatchObject({
      status: 'streaming',
      content: [{ type: 'text', text: '' }],
    });
  });

  it('archives a conversation and moves selection to another visible conversation', () => {
    useChatStore.getState().hydrateConversations(structuredClone(mockConversations));
    useChatStore.getState().setSelectedConversationId('conv-demo-flow');
    useChatStore.getState().toggleConversationArchive('conv-demo-flow');

    expect(useChatStore.getState().selectedConversationId).not.toBe('conv-demo-flow');
  });
});
