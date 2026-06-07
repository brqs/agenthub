import { useChatStore } from './chatStore';
import { mockConversations, type DemoMessage } from '@/lib/mockData';
import type { Message } from '@/lib/types';

function resetChatStore() {
  useChatStore.getState().clearChat();
}

function addStreamingMessage(
  conversationId = 'conv-demo-flow',
  messageId = '00000000-0000-4000-8000-000000000099',
): string {
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
          title: '娴嬭瘯浠诲姟',
          tasks: [{ id: 'plan', agent_id: 'orchestrator', title: '瑙勫垝', status: 'running' }],
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
        { type: 'task_card', title: '娴嬭瘯浠诲姟' },
        { type: 'text', text: 'hello' },
        { type: 'tool_call', call_id: 'call-write', status: 'ok', output_preview: 'wrote file' },
      ],
    });
  });

  it('marks streaming messages interrupted without converting them to errors', () => {
    const messageId = addStreamingMessage();
    const store = useChatStore.getState();
    store.applyStreamEvent(messageId, {
      event: 'block_start',
      data: {
        block_index: 0,
        block_type: 'task_card',
        metadata: {
          title: 'Plan',
          tasks: [{ id: 'build', agent_id: 'codex-helper', title: 'Build', status: 'running' }],
        },
      },
    });
    store.applyStreamEvent(messageId, { event: 'interrupted', data: { message_id: messageId } });

    expect(useChatStore.getState().messagesByConversation['conv-demo-flow'][0]).toMatchObject({
      status: 'interrupted',
      content: [
        {
          type: 'task_card',
          tasks: [{ id: 'build', status: 'interrupted' }],
        },
      ],
    });
  });

  it('appends and removes queued user messages locally', () => {
    useChatStore.getState().hydrateConversations(structuredClone(mockConversations));
    const queued = createMessage({
      id: '00000000-0000-4000-8000-000000000251',
      role: 'user',
      status: 'queued',
      content: [{ type: 'text', text: 'queued next' }],
    });

    useChatStore.getState().appendQueuedMessage('conv-demo-flow', queued);

    expect(useChatStore.getState().messagesByConversation['conv-demo-flow']).toEqual([queued]);
    expect(
      useChatStore
        .getState()
        .conversations.find((conversation) => conversation.id === 'conv-demo-flow')
        ?.last_message_preview,
    ).toBe('1 条消息已排队');

    useChatStore.getState().removeMessageLocal(queued.id);
    expect(useChatStore.getState().messagesByConversation['conv-demo-flow']).toEqual([]);
  });

  it('starts the next queued exchange from terminal stream payload', () => {
    const currentMessageId = addStreamingMessage(
      'conv-demo-flow',
      '00000000-0000-4000-8000-000000000252',
    );
    useChatStore.getState().startActiveStream({
      id: currentMessageId,
      conversation_id: 'conv-demo-flow',
      agent_id: 'orchestrator',
    });
    const queuedUser = createMessage({
      id: '00000000-0000-4000-8000-000000000253',
      role: 'user',
      status: 'done',
      created_at: '2026-05-31T00:01:00.000Z',
      content: [{ type: 'text', text: 'queued next' }],
    });
    const queuedAgent = createMessage({
      id: '00000000-0000-4000-8000-000000000254',
      role: 'agent',
      agent_id: 'orchestrator',
      reply_to_id: queuedUser.id,
      status: 'pending',
      created_at: '2026-05-31T00:01:00.000Z',
      content: [],
    });

    useChatStore.getState().applyStreamEvent(currentMessageId, {
      event: 'done',
      data: {
        message_id: currentMessageId,
        total_blocks: 0,
        queued_next: {
          user_message: queuedUser,
          agent_message: queuedAgent,
          queue_remaining_count: 0,
        },
      },
    });

    const messages = useChatStore.getState().messagesByConversation['conv-demo-flow'];
    expect(messages.map((message) => message.id)).toEqual([
      currentMessageId,
      queuedUser.id,
      queuedAgent.id,
    ]);
    expect(useChatStore.getState().activeStreams[queuedAgent.id]).toMatchObject({
      messageId: queuedAgent.id,
      conversationId: 'conv-demo-flow',
      agentId: 'orchestrator',
    });
  });

  it('clears active streams when hydrate returns interrupted', () => {
    const message = createMessage({
      id: '00000000-0000-4000-8000-000000000301',
      role: 'agent',
      agent_id: 'orchestrator',
      status: 'streaming',
    });
    useChatStore.getState().hydrateMessages('conv-demo-flow', [message]);

    expect(useChatStore.getState().activeStreams[message.id]).toBeDefined();

    useChatStore.getState().hydrateMessages('conv-demo-flow', [
      {
        ...message,
        status: 'interrupted',
        content: [{ type: 'text', text: '已打断本次回复，可以继续补充要求。' }],
      },
    ]);

    expect(useChatStore.getState().activeStreams[message.id]).toBeUndefined();
    expect(useChatStore.getState().messagesByConversation['conv-demo-flow'][0].status).toBe(
      'interrupted',
    );
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

  it('applies process stream events and process deltas', () => {
    const messageId = addStreamingMessage();
    const store = useChatStore.getState();
    store.applyStreamEvent(messageId, {
      event: 'block_start',
      data: {
        block_index: 0,
        block_type: 'process',
        agent_id: 'orchestrator',
        metadata: {
          title: '执行过程',
          status: 'partial',
          default_collapsed: false,
          summary: '公开执行过程部分完成。',
          steps: [
            {
              id: 'summary-step',
              label: '公开摘要',
              kind: 'summary',
              status: 'done',
              detail: '已整理。',
            },
          ],
          metadata: { source: 'orchestrator_process' },
        },
      },
    });
    store.applyStreamEvent(messageId, {
      event: 'delta',
      data: {
        block_index: 0,
        metadata: {
          process_delta: {
            op: 'upsert_step',
            step: {
              id: 'summary-step',
              label: '公开摘要',
              kind: 'summary',
              status: 'running',
              detail: '正在整理。',
            },
          },
        },
      },
    });
    store.applyStreamEvent(messageId, {
      event: 'delta',
      data: {
        block_index: 0,
        metadata: {
          process_delta: {
            op: 'set_summary',
            status: 'done',
            summary: '公开执行过程已完成。',
          },
        },
      },
    });

    expect(
      useChatStore.getState().messagesByConversation['conv-demo-flow'][0].content[0],
    ).toMatchObject({
      type: 'process',
      agent_id: 'orchestrator',
      title: '执行过程',
      status: 'done',
      summary: '公开执行过程已完成。',
      steps: [
        {
          id: 'summary-step',
          label: '公开摘要',
          kind: 'summary',
          status: 'running',
          detail: '正在整理。',
        },
      ],
    });
    expect(
      useChatStore.getState().messagesByConversation['conv-demo-flow'][0].content[0],
    ).not.toHaveProperty('text');
  });

  it('applies clarification stream events as clarification blocks', () => {
    const messageId = addStreamingMessage();
    const store = useChatStore.getState();
    store.applyStreamEvent(messageId, {
      event: 'block_start',
      data: {
        block_index: 0,
        block_type: 'clarification',
        agent_id: 'orchestrator',
        metadata: {
          agent_id: 'orchestrator',
          mode: 'grill_me',
          title: 'Needs clarification',
          status: 'waiting',
          current_question: {
            id: 'scope',
            question: 'What scope should we implement?',
            reason: 'This changes the implementation plan.',
            recommended_answer: 'Use the recommended static web app scope.',
            options: ['Use recommendation'],
            status: 'pending',
          },
          questions: [],
          metadata: { original_request: 'build a game' },
        },
      },
    });

    expect(
      useChatStore.getState().messagesByConversation['conv-demo-flow'][0].content[0],
    ).toMatchObject({
      type: 'clarification',
      agent_id: 'orchestrator',
      mode: 'grill_me',
      title: 'Needs clarification',
      status: 'waiting',
      current_question: {
        id: 'scope',
        question: 'What scope should we implement?',
        recommended_answer: 'Use the recommended static web app scope.',
      },
    });
  });

  it('routes orchestrator child message events into independent agent messages', () => {
    const parentId = addStreamingMessage('conv-demo-flow', 'parent-orchestrator-message');
    const store = useChatStore.getState();

    store.applyStreamEvent(parentId, {
      event: 'message_start',
      data: {
        message_id: 'child-codex-message',
        conversation_id: 'conv-demo-flow',
        agent_id: 'codex-helper',
        reply_to_id: 'user-message-1',
        created_at: '2026-05-31T00:00:01.000Z',
        status: 'streaming',
      },
    });
    store.applyStreamEvent(parentId, {
      event: 'block_start',
      data: {
        message_id: 'child-codex-message',
        block_index: 0,
        block_type: 'process',
        agent_id: 'codex-helper',
        metadata: {
          title: '思考与执行',
          status: 'running',
          default_collapsed: false,
          steps: [],
        },
      },
    });
    store.applyStreamEvent(parentId, {
      event: 'delta',
      data: {
        message_id: 'child-codex-message',
        block_index: 0,
        metadata: {
          process_delta: {
            op: 'upsert_step',
            step: {
              id: 'architecture',
              label: '设计执行方案',
              kind: 'planning',
              status: 'running',
              agent_id: 'codex-helper',
            },
          },
        },
      },
    });
    store.applyStreamEvent(parentId, {
      event: 'block_start',
      data: {
        message_id: 'child-codex-message',
        block_index: 1,
        block_type: 'text',
        agent_id: 'codex-helper',
      },
    });
    store.applyStreamEvent(parentId, {
      event: 'delta',
      data: {
        message_id: 'child-codex-message',
        block_index: 1,
        text_delta: '已生成 planning.md',
        agent_id: 'codex-helper',
      },
    });
    store.applyStreamEvent(parentId, {
      event: 'message_done',
      data: {
        message_id: 'child-codex-message',
        conversation_id: 'conv-demo-flow',
        agent_id: 'codex-helper',
        status: 'done',
        total_blocks: 2,
      },
    });

    const messages = useChatStore.getState().messagesByConversation['conv-demo-flow'];
    const parent = messages.find((message) => message.id === parentId);
    const child = messages.find((message) => message.id === 'child-codex-message');

    expect(parent?.content).toEqual([]);
    expect(child).toMatchObject({
      id: 'child-codex-message',
      role: 'agent',
      agent_id: 'codex-helper',
      reply_to_id: 'user-message-1',
      status: 'done',
    });
    expect(child?.content).toMatchObject([
      {
        type: 'process',
        agent_id: 'codex-helper',
        steps: [{ id: 'architecture', label: '设计执行方案', status: 'running' }],
      },
      { type: 'text', agent_id: 'codex-helper', text: '已生成 planning.md' },
    ]);
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

  it('updates orchestrator task card progress by exact agent switch task', () => {
    const messageId = addStreamingMessage();
    const store = useChatStore.getState();
    store.applyStreamEvent(messageId, {
      event: 'block_start',
      data: {
        block_index: 0,
        block_type: 'task_card',
        metadata: {
          title: 'Orchestrator plan',
          tasks: [
            { id: 'task-a', agent_id: 'claude-code', title: 'Build HTML', status: 'pending' },
            { id: 'task-b', agent_id: 'claude-code', title: 'Review HTML', status: 'pending' },
          ],
        },
      },
    });

    store.applyStreamEvent(messageId, {
      event: 'agent_switch',
      data: { from_agent: 'orchestrator', to_agent: 'claude-code', task: 'Build HTML' },
    });

    expect(
      useChatStore.getState().messagesByConversation['conv-demo-flow'][0].content[0],
    ).toMatchObject({
      type: 'task_card',
      tasks: [
        { id: 'task-a', status: 'running' },
        { id: 'task-b', status: 'pending' },
      ],
    });

    store.applyStreamEvent(messageId, {
      event: 'agent_switch',
      data: { from_agent: 'orchestrator', to_agent: 'claude-code', task: 'Review HTML' },
    });

    expect(
      useChatStore.getState().messagesByConversation['conv-demo-flow'][0].content[0],
    ).toMatchObject({
      type: 'task_card',
      tasks: [
        { id: 'task-a', status: 'done' },
        { id: 'task-b', status: 'running' },
      ],
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

  it('ignores late stream errors after a message is done', () => {
    const messageId = addStreamingMessage();
    const store = useChatStore.getState();
    store.applyStreamEvent(messageId, {
      event: 'block_start',
      data: { block_index: 0, block_type: 'text' },
    });
    store.applyStreamEvent(messageId, {
      event: 'delta',
      data: { block_index: 0, text_delta: 'finished output' },
    });
    store.applyStreamEvent(messageId, { event: 'done', data: { total_blocks: 1 } });
    store.applyStreamEvent(messageId, {
      event: 'error',
      data: { error: 'late transport error' },
    });

    expect(useChatStore.getState().messagesByConversation['conv-demo-flow'][0]).toMatchObject({
      status: 'done',
      content: [{ type: 'text', text: 'finished output' }],
    });
  });

  it('replaces streaming conversation preview when a stream finishes', () => {
    useChatStore.getState().hydrateConversations([
      {
        ...structuredClone(mockConversations[0]!),
        id: 'conv-preview-done',
        last_message_preview: null,
      },
    ]);
    const messageId = addStreamingMessage('conv-preview-done');
    const store = useChatStore.getState();

    store.applyStreamEvent(messageId, {
      event: 'block_start',
      data: { block_index: 0, block_type: 'text' },
    });
    expect(useChatStore.getState().conversations[0].last_message_preview).toBe(
      'Agent 正在流式回复...',
    );

    store.applyStreamEvent(messageId, {
      event: 'delta',
      data: { block_index: 0, text_delta: 'finished output' },
    });
    store.applyStreamEvent(messageId, { event: 'done', data: { total_blocks: 1 } });

    expect(useChatStore.getState().conversations[0].last_message_preview).toBe(
      'finished output',
    );
  });

  it('lets hydrated done snapshots recover a locally errored message', () => {
    const messageId = addStreamingMessage('conv-hydrate-done');
    const store = useChatStore.getState();
    store.applyStreamEvent(messageId, {
      event: 'error',
      data: { error: 'local stream closed' },
    });

    store.hydrateMessages('conv-hydrate-done', [
      {
        id: messageId,
        conversation_id: 'conv-hydrate-done',
        role: 'agent',
        agent_id: 'claude-code',
        reply_to_id: null,
        status: 'done',
        is_pinned: false,
        created_at: '2026-05-31T00:00:00.000Z',
        content: [{ type: 'text', text: 'server says done' }],
      },
    ]);

    expect(useChatStore.getState().messagesByConversation['conv-hydrate-done'][0]).toMatchObject({
      status: 'done',
      content: [{ type: 'text', text: 'server says done' }],
    });
  });

  it('tracks multiple active streams independently', () => {
    const first = addStreamingMessage('conv-a', '00000000-0000-4000-8000-0000000000a1');
    const second = addStreamingMessage('conv-b', '00000000-0000-4000-8000-0000000000b2');
    useChatStore.getState().startActiveStream({
      id: first,
      conversation_id: 'conv-a',
      agent_id: 'claude-code',
    });
    useChatStore.getState().startActiveStream({
      id: second,
      conversation_id: 'conv-b',
      agent_id: 'orchestrator',
    });

    expect(Object.keys(useChatStore.getState().activeStreams).sort()).toEqual(
      [first, second].sort(),
    );

    useChatStore.getState().applyStreamEvent(first, {
      event: 'done',
      data: { total_blocks: 0 },
    });
    useChatStore.getState().finishActiveStream(first);

    expect(useChatStore.getState().activeStreams[first]).toBeUndefined();
    expect(useChatStore.getState().activeStreams[second]).toMatchObject({
      conversationId: 'conv-b',
    });
    expect(useChatStore.getState().messagesByConversation['conv-a'][0].status).toBe('done');
    expect(useChatStore.getState().messagesByConversation['conv-b'][0].status).toBe(
      'streaming',
    );
  });

  it('does not clobber active streaming content during hydration', () => {
    const messageId = addStreamingMessage('conv-active');
    useChatStore.getState().startActiveStream({
      id: messageId,
      conversation_id: 'conv-active',
      agent_id: 'orchestrator',
    });
    useChatStore.getState().applyStreamEvent(messageId, {
      event: 'block_start',
      data: { block_index: 0, block_type: 'text' },
    });
    useChatStore.getState().applyStreamEvent(messageId, {
      event: 'delta',
      data: { block_index: 0, text_delta: 'local stream text' },
    });

    useChatStore.getState().hydrateMessages('conv-active', [
      {
        id: messageId,
        conversation_id: 'conv-active',
        role: 'agent',
        agent_id: 'orchestrator',
        reply_to_id: null,
        status: 'streaming',
        is_pinned: false,
        created_at: '2026-05-31T00:00:00.000Z',
        content: [],
      },
    ]);

    expect(useChatStore.getState().messagesByConversation['conv-active'][0].content).toEqual([
      { type: 'text', agent_id: null, text: 'local stream text' },
    ]);
  });

  it('keeps active streaming messages missing from the hydrated page', () => {
    const messageId = addStreamingMessage('conv-active-missing');
    useChatStore.getState().startActiveStream({
      id: messageId,
      conversation_id: 'conv-active-missing',
      agent_id: 'orchestrator',
    });
    useChatStore.getState().applyStreamEvent(messageId, {
      event: 'block_start',
      data: { block_index: 0, block_type: 'code', metadata: { language: 'html' } },
    });
    useChatStore.getState().applyStreamEvent(messageId, {
      event: 'delta',
      data: { block_index: 0, code_delta: '<!doctype html>' },
    });

    useChatStore.getState().hydrateMessages('conv-active-missing', [
      {
        id: '00000000-0000-4000-8000-000000000124',
        conversation_id: 'conv-active-missing',
        role: 'user',
        agent_id: null,
        reply_to_id: null,
        status: 'done',
        is_pinned: false,
        created_at: '2026-05-30T00:00:00.000Z',
        content: [{ type: 'text', text: 'older server message' }],
      },
    ]);

    expect(
      useChatStore
        .getState()
        .messagesByConversation['conv-active-missing'].map((message) => message.id),
    ).toEqual(['00000000-0000-4000-8000-000000000124', messageId]);
    expect(useChatStore.getState().messagesByConversation['conv-active-missing'][1].content).toEqual([
      { type: 'code', agent_id: null, language: 'html', code: '<!doctype html>' },
    ]);
  });

  it('keeps the parent user message when an active stream is missing from hydration', () => {
    const userMessage = createMessage({
      id: '00000000-0000-4000-8000-000000000125',
      conversation_id: 'conv-active-parent-empty',
      role: 'user',
      created_at: '2026-05-31T00:00:00.000Z',
      content: [{ type: 'text', text: 'build a game' }],
    }) as DemoMessage;
    const agentMessage = createMessage({
      id: '00000000-0000-4000-8000-000000000126',
      conversation_id: 'conv-active-parent-empty',
      role: 'agent',
      agent_id: 'orchestrator',
      reply_to_id: userMessage.id,
      status: 'streaming',
      created_at: '2026-05-31T00:00:01.000Z',
      content: [{ type: 'text', text: 'working' }],
    }) as DemoMessage;

    useChatStore.setState((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        'conv-active-parent-empty': [userMessage, agentMessage],
      },
    }));
    useChatStore.getState().startActiveStream({
      id: agentMessage.id,
      conversation_id: 'conv-active-parent-empty',
      agent_id: 'orchestrator',
    });

    useChatStore.getState().hydrateMessages('conv-active-parent-empty', []);

    expect(
      useChatStore
        .getState()
        .messagesByConversation['conv-active-parent-empty'].map((message) => message.id),
    ).toEqual([userMessage.id, agentMessage.id]);
  });

  it('keeps the parent user message when hydration only includes the active stream', () => {
    const userMessage = createMessage({
      id: '00000000-0000-4000-8000-000000000127',
      conversation_id: 'conv-active-parent-partial',
      role: 'user',
      created_at: '2026-05-31T00:00:00.000Z',
      content: [{ type: 'text', text: 'make a page' }],
    }) as DemoMessage;
    const agentMessage = createMessage({
      id: '00000000-0000-4000-8000-000000000128',
      conversation_id: 'conv-active-parent-partial',
      role: 'agent',
      agent_id: 'orchestrator',
      reply_to_id: userMessage.id,
      status: 'streaming',
      created_at: '2026-05-31T00:00:01.000Z',
      content: [{ type: 'text', text: 'local partial' }],
    }) as DemoMessage;

    useChatStore.setState((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        'conv-active-parent-partial': [userMessage, agentMessage],
      },
    }));
    useChatStore.getState().startActiveStream({
      id: agentMessage.id,
      conversation_id: 'conv-active-parent-partial',
      agent_id: 'orchestrator',
    });

    useChatStore.getState().hydrateMessages('conv-active-parent-partial', [
      {
        ...agentMessage,
        content: [],
      },
    ]);

    expect(
      useChatStore
        .getState()
        .messagesByConversation['conv-active-parent-partial'].map((message) => message.id),
    ).toEqual([userMessage.id, agentMessage.id]);
    expect(
      useChatStore.getState().messagesByConversation['conv-active-parent-partial'][1].content,
    ).toEqual([{ type: 'text', text: 'local partial' }]);
  });

  it('does not keep unrelated local user messages missing from hydration', () => {
    const userMessage = createMessage({
      id: '00000000-0000-4000-8000-000000000129',
      conversation_id: 'conv-unrelated-local',
      role: 'user',
      created_at: '2026-05-31T00:00:00.000Z',
      content: [{ type: 'text', text: 'stale local only' }],
    }) as DemoMessage;

    useChatStore.setState((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        'conv-unrelated-local': [userMessage],
      },
    }));

    useChatStore.getState().hydrateMessages('conv-unrelated-local', []);

    expect(useChatStore.getState().messagesByConversation['conv-unrelated-local']).toEqual([]);
  });

  it('uses the server snapshot when hydration includes the same user message', () => {
    const userMessage = createMessage({
      id: '00000000-0000-4000-8000-000000000130',
      conversation_id: 'conv-server-user-wins',
      role: 'user',
      created_at: '2026-05-31T00:00:00.000Z',
      content: [{ type: 'text', text: 'local pending text' }],
    }) as DemoMessage;
    const agentMessage = createMessage({
      id: '00000000-0000-4000-8000-000000000131',
      conversation_id: 'conv-server-user-wins',
      role: 'agent',
      agent_id: 'orchestrator',
      reply_to_id: userMessage.id,
      status: 'streaming',
      created_at: '2026-05-31T00:00:01.000Z',
      content: [{ type: 'text', text: 'local partial' }],
    }) as DemoMessage;

    useChatStore.setState((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        'conv-server-user-wins': [userMessage, agentMessage],
      },
    }));
    useChatStore.getState().startActiveStream({
      id: agentMessage.id,
      conversation_id: 'conv-server-user-wins',
      agent_id: 'orchestrator',
    });

    useChatStore.getState().hydrateMessages('conv-server-user-wins', [
      {
        ...userMessage,
        content: [{ type: 'text', text: 'server text' }],
      },
    ]);

    expect(useChatStore.getState().messagesByConversation['conv-server-user-wins'][0]).toMatchObject({
      id: userMessage.id,
      content: [{ type: 'text', text: 'server text' }],
    });
  });

  it('recovers hydrated streaming messages as active streams', () => {
    useChatStore.getState().hydrateMessages('conv-stale', [
      {
        id: '00000000-0000-4000-8000-000000000123',
        conversation_id: 'conv-stale',
        role: 'agent',
        agent_id: 'claude-code',
        reply_to_id: null,
        status: 'streaming',
        is_pinned: false,
        created_at: '2026-05-31T00:00:00.000Z',
        content: [],
      },
    ]);

    expect(useChatStore.getState().messagesByConversation['conv-stale'][0]).toMatchObject({
      status: 'streaming',
      content: [],
    });
    expect(
      useChatStore.getState().activeStreams['00000000-0000-4000-8000-000000000123'],
    ).toMatchObject({
      conversationId: 'conv-stale',
      agentId: 'claude-code',
    });
  });

  it('clears active streams when hydrated snapshots are terminal', () => {
    const messageId = addStreamingMessage('conv-terminal');
    useChatStore.getState().startActiveStream({
      id: messageId,
      conversation_id: 'conv-terminal',
      agent_id: 'orchestrator',
    });

    useChatStore.getState().hydrateMessages('conv-terminal', [
      {
        id: messageId,
        conversation_id: 'conv-terminal',
        role: 'agent',
        agent_id: 'orchestrator',
        reply_to_id: null,
        status: 'done',
        is_pinned: false,
        created_at: '2026-05-31T00:00:00.000Z',
        content: [{ type: 'text', text: 'server done' }],
      },
    ]);

    expect(useChatStore.getState().activeStreams[messageId]).toBeUndefined();
    expect(useChatStore.getState().messagesByConversation['conv-terminal'][0]).toMatchObject({
      status: 'done',
      content: [{ type: 'text', text: 'server done' }],
    });
  });

  it('preserves active local content when a streaming server snapshot is empty', () => {
    const messageId = addStreamingMessage('conv-stale-content');
    useChatStore.getState().startActiveStream({
      id: messageId,
      conversation_id: 'conv-stale-content',
      agent_id: 'orchestrator',
    });
    useChatStore.getState().applyStreamEvent(messageId, {
      event: 'block_start',
      data: { block_index: 0, block_type: 'text' },
    });
    useChatStore.getState().applyStreamEvent(messageId, {
      event: 'delta',
      data: { block_index: 0, text_delta: 'partial local output' },
    });

    useChatStore.getState().hydrateMessages('conv-stale-content', [
      {
        id: messageId,
        conversation_id: 'conv-stale-content',
        role: 'agent',
        agent_id: 'orchestrator',
        reply_to_id: null,
        status: 'streaming',
        is_pinned: false,
        created_at: '2026-05-31T00:00:00.000Z',
        content: [],
      },
    ]);

    expect(useChatStore.getState().messagesByConversation['conv-stale-content'][0]).toMatchObject({
      status: 'streaming',
      content: [{ type: 'text', text: 'partial local output' }],
    });
  });

  it('archives a conversation and moves selection to another visible conversation', () => {
    useChatStore.getState().hydrateConversations(structuredClone(mockConversations));
    useChatStore.getState().setSelectedConversationId('conv-demo-flow');
    useChatStore.getState().toggleConversationArchive('conv-demo-flow');

    expect(useChatStore.getState().selectedConversationId).not.toBe('conv-demo-flow');
  });
});
