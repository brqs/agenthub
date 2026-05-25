import { create } from 'zustand';
import {
  createMockReply,
  getAgent,
  mockConversations,
  mockMessages,
  type DemoContentBlock,
  type DemoConversation,
  type DemoMessage,
  type TaskCardBlock,
  type TaskStatus,
} from '@/lib/mockData';
import type { Conversation, Message, StreamEvent } from '@/lib/types';

interface ChatState {
  conversations: DemoConversation[];
  messagesByConversation: Record<string, DemoMessage[]>;
  selectedConversationId: string;
  search: string;
  highlightedMessageId: string | null;
  createConversation: (input: {
    title: string;
    mode: DemoConversation['mode'];
    agentIds: string[];
  }) => DemoConversation;
  setSelectedConversationId: (conversationId: string) => void;
  setSearch: (search: string) => void;
  setHighlightedMessageId: (messageId: string | null) => void;
  toggleMessagePin: (messageId: string) => void;
  toggleConversationPin: (conversationId: string) => void;
  toggleConversationArchive: (conversationId: string) => void;
  createPendingExchange: (conversationId: string, text: string) => { agentMessageId: string } | null;
  applyStreamEvent: (messageId: string, event: StreamEvent) => void;
  resetMessageForRetry: (messageId: string) => void;
  /** Prepend a freshly created conversation (returned by POST /conversations). */
  addConversation: (conversation: Conversation) => void;
  /** Replace the conversation list (used to mirror server state in API mode). */
  hydrateConversations: (conversations: Conversation[]) => void;
  /** Replace messages for a single conversation (used on initial fetch in API mode). */
  hydrateMessages: (conversationId: string, messages: Message[]) => void;
  /** Append the {user_message, agent_message} pair returned by POST /messages. */
  appendRemoteExchange: (
    conversationId: string,
    userMessage: Message,
    agentMessage: Message,
  ) => void;
}

function createUserMessage(conversationId: string, text: string): DemoMessage {
  return {
    id: `user-${Date.now()}`,
    conversation_id: conversationId,
    role: 'user',
    agent_id: null,
    content: [{ type: 'text', text }],
    reply_to_id: null,
    status: 'done',
    is_pinned: false,
    created_at: new Date().toISOString(),
  };
}

function getTargetAgent(conversation: DemoConversation, text: string): string {
  if (conversation.mode === 'group') {
    const mentionedAgent = conversation.agent_ids.find((agentId) => {
      const normalized = text.toLowerCase();
      return normalized.includes(`@${agentId.toLowerCase()}`);
    });
    if (mentionedAgent) return mentionedAgent;

    return conversation.agent_ids.includes('orchestrator')
      ? 'orchestrator'
      : conversation.agent_ids[0];
  }

  return conversation.agent_ids[0];
}

function appendText(blocks: DemoContentBlock[], text: string): DemoContentBlock[] {
  const [firstBlock, ...rest] = blocks;
  if (!firstBlock || firstBlock.type !== 'text') {
    return [{ type: 'text', text }, ...blocks];
  }

  return [{ ...firstBlock, text: `${firstBlock.text}${text}` }, ...rest];
}

function isTaskCardMetadata(value: unknown): value is Omit<TaskCardBlock, 'type'> {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as { title?: unknown; tasks?: unknown };
  return typeof candidate.title === 'string' && Array.isArray(candidate.tasks);
}

function createTaskCard(metadata: Record<string, unknown> | undefined): TaskCardBlock {
  const fallback: Omit<TaskCardBlock, 'type'> = {
    title: '群聊协作任务流',
    tasks: [],
  };
  const value = isTaskCardMetadata(metadata) ? metadata : fallback;
  return {
    type: 'task_card',
    title: value.title,
    tasks: value.tasks.map((task) => ({
      id: String(task.id),
      agent_id: String(task.agent_id),
      title: String(task.title),
      status: task.status as TaskStatus,
    })),
  };
}

function updateTaskStatuses(
  blocks: DemoContentBlock[],
  event: Extract<StreamEvent, { event: 'agent_switch' }>,
): DemoContentBlock[] {
  return blocks.map((block) => {
    if (block.type !== 'task_card') return block;
    return {
      ...block,
      tasks: block.tasks.map((task) => {
        if (task.agent_id === event.data.from_agent && task.status === 'running') {
          return { ...task, status: 'done' as const };
        }
        if (task.agent_id === event.data.to_agent) {
          return { ...task, status: 'running' as const };
        }
        return task;
      }),
    };
  });
}

function completeRunningTasks(blocks: DemoContentBlock[]): DemoContentBlock[] {
  return blocks.map((block) => {
    if (block.type !== 'task_card') return block;
    return {
      ...block,
      tasks: block.tasks.map((task) =>
        task.status === 'running' ? { ...task, status: 'done' as const } : task,
      ),
    };
  });
}

function applyDelta(blocks: DemoContentBlock[], event: StreamEvent): DemoContentBlock[] {
  if (event.event === 'block_start') {
    const next = [...blocks];
    if (event.data.block_type === 'task_card') {
      next[event.data.block_index] = createTaskCard(event.data.metadata);
    } else if (event.data.block_type === 'code') {
      next[event.data.block_index] = {
        type: 'code',
        language: (event.data.metadata?.language as string) || 'text',
        code: '',
      };
    } else {
      next[event.data.block_index] = { type: 'text', text: '' };
    }
    return next;
  }

  if (event.event === 'agent_switch') {
    const next = updateTaskStatuses(blocks, event);
    next.push({
      type: 'agent_switch',
      from_agent: event.data.from_agent,
      to_agent: event.data.to_agent,
      task: event.data.task ?? `${getAgent(event.data.to_agent)?.name ?? event.data.to_agent} 接手任务`,
    });
    return next;
  }

  if (event.event !== 'delta') return blocks;

  const next = [...blocks];
  const block = next[event.data.block_index];
  if (!block) return next;

  if (block.type === 'text' && event.data.text_delta) {
    next[event.data.block_index] = { ...block, text: `${block.text}${event.data.text_delta}` };
  }
  if (block.type === 'code' && event.data.code_delta) {
    next[event.data.block_index] = { ...block, code: `${block.code}${event.data.code_delta}` };
  }
  return next;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: mockConversations,
  messagesByConversation: mockMessages,
  selectedConversationId: mockConversations[0]?.id ?? '',
  search: '',
  highlightedMessageId: null,
  createConversation: (input) => {
    const createdAt = new Date().toISOString();
    const conversation: DemoConversation = {
      id: `conv-${Date.now()}`,
      title: input.title,
      mode: input.mode,
      agent_ids: input.agentIds,
      is_pinned: false,
      is_archived: false,
      last_message_at: createdAt,
      last_message_preview: '新会话已创建，发送第一条消息开始协作。',
      created_at: createdAt,
    };

    set((state) => ({
      conversations: [conversation, ...state.conversations],
      messagesByConversation: {
        ...state.messagesByConversation,
        [conversation.id]: [],
      },
      selectedConversationId: conversation.id,
    }));

    return conversation;
  },
  setSelectedConversationId: (conversationId) => set({ selectedConversationId: conversationId }),
  setSearch: (search) => set({ search }),
  setHighlightedMessageId: (messageId) => set({ highlightedMessageId: messageId }),
  toggleMessagePin: (messageId) => {
    set((state) => ({
      messagesByConversation: Object.fromEntries(
        Object.entries(state.messagesByConversation).map(([conversationId, messages]) => [
          conversationId,
          messages.map((message) =>
            message.id === messageId ? { ...message, is_pinned: !message.is_pinned } : message,
          ),
        ]),
      ),
    }));
  },
  toggleConversationPin: (conversationId) => {
    set((state) => ({
      conversations: state.conversations.map((conversation) =>
        conversation.id === conversationId
          ? { ...conversation, is_pinned: !conversation.is_pinned }
          : conversation,
      ),
    }));
  },
  toggleConversationArchive: (conversationId) => {
    set((state) => {
      const target = state.conversations.find((conversation) => conversation.id === conversationId);
      const willArchive = !target?.is_archived;
      const nextVisible = state.conversations.find(
        (conversation) => conversation.id !== conversationId && !conversation.is_archived,
      );
      return {
        conversations: state.conversations.map((conversation) =>
          conversation.id === conversationId
            ? { ...conversation, is_archived: !conversation.is_archived }
            : conversation,
        ),
        selectedConversationId:
          willArchive && state.selectedConversationId === conversationId
            ? nextVisible?.id ?? ''
            : state.selectedConversationId,
      };
    });
  },
  createPendingExchange: (conversationId, text) => {
    const conversation = get().conversations.find((item) => item.id === conversationId);
    if (!conversation) return null;

    const userMessage = createUserMessage(conversationId, text);
    const agentId = getTargetAgent(conversation, text);
    const reply = createMockReply(conversationId, agentId);

    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [conversationId]: [
          ...(state.messagesByConversation[conversationId] ?? []),
          userMessage,
          reply,
        ],
      },
      conversations: state.conversations.map((item) =>
        item.id === conversationId
          ? {
              ...item,
              last_message_at: userMessage.created_at,
              last_message_preview: text,
            }
          : item,
      ),
    }));

    return { agentMessageId: reply.id };
  },
  applyStreamEvent: (messageId, event) => {
    set((state) => {
      let touchedConversationId: string | null = null;
      const nextMessagesByConversation = Object.fromEntries(
        Object.entries(state.messagesByConversation).map(([conversationId, messages]) => {
          const nextMessages = messages.map((message) => {
            if (message.id !== messageId) return message;
            touchedConversationId = conversationId;
            if (event.event === 'start') {
              return { ...message, status: 'streaming' as const };
            }
            if (event.event === 'done') {
              return { ...message, status: 'done' as const, content: completeRunningTasks(message.content) };
            }
            if (event.event === 'error') {
              return {
                ...message,
                status: 'error' as const,
                content: appendText(
                  message.content,
                  `\n\n调用失败：${event.data.error ?? event.data.error_code ?? 'unknown error'}`,
                ),
              };
            }
            return {
              ...message,
              content: applyDelta(message.content, event),
            };
          });
          return [conversationId, nextMessages];
        }),
      );

      const nextConversations = touchedConversationId
        ? state.conversations.map((conversation) =>
            conversation.id === touchedConversationId
              ? {
                  ...conversation,
                  last_message_at: new Date().toISOString(),
                  last_message_preview: 'Agent 正在流式回复...',
                }
              : conversation,
          )
        : state.conversations;

      return {
        messagesByConversation: nextMessagesByConversation,
        conversations: nextConversations,
      };
    });
  },
  resetMessageForRetry: (messageId) => {
    set((state) => ({
      messagesByConversation: Object.fromEntries(
        Object.entries(state.messagesByConversation).map(([conversationId, messages]) => [
          conversationId,
          messages.map((message) =>
            message.id === messageId
              ? {
                  ...message,
                  status: 'streaming' as const,
                  content: [{ type: 'text', text: '' }],
                }
              : message,
          ),
        ]),
      ),
    }));
  },
  addConversation: (conversation) => {
    set((state) => ({
      conversations: [conversation as DemoConversation, ...state.conversations],
      messagesByConversation: {
        ...state.messagesByConversation,
        [conversation.id]: state.messagesByConversation[conversation.id] ?? [],
      },
      selectedConversationId: conversation.id,
    }));
  },
  hydrateConversations: (conversations) => {
    set((state) => {
      const remoteIds = new Set(conversations.map((c) => c.id));
      const selected = state.selectedConversationId;
      const nextSelected =
        selected && remoteIds.has(selected) ? selected : conversations[0]?.id ?? '';
      return {
        conversations: conversations as DemoConversation[],
        selectedConversationId: nextSelected,
      };
    });
  },
  hydrateMessages: (conversationId, messages) => {
    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [conversationId]: messages as DemoMessage[],
      },
    }));
  },
  appendRemoteExchange: (conversationId, userMessage, agentMessage) => {
    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [conversationId]: [
          ...(state.messagesByConversation[conversationId] ?? []),
          userMessage as DemoMessage,
          agentMessage as DemoMessage,
        ],
      },
      conversations: state.conversations.map((item) =>
        item.id === conversationId
          ? {
              ...item,
              last_message_at: userMessage.created_at,
              last_message_preview:
                (userMessage.content?.[0] as { text?: string } | undefined)?.text ??
                item.last_message_preview ??
                null,
            }
          : item,
      ),
    }));
  },
}));
