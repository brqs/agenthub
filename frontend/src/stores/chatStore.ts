import { create } from 'zustand';
import {
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
  setSelectedConversationId: (conversationId: string) => void;
  setSearch: (search: string) => void;
  setHighlightedMessageId: (messageId: string | null) => void;
  toggleMessagePin: (messageId: string) => void;
  toggleConversationPin: (conversationId: string) => void;
  toggleConversationArchive: (conversationId: string) => void;
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
  updateConversationLocal: (conversation: Conversation) => void;
  updateMessageLocal: (message: Message) => void;
  replaceMessageLocal: (oldMessageId: string, message: Message) => void;
  clearChat: () => void;
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

function applyToolCall(
  blocks: DemoContentBlock[],
  event: Extract<StreamEvent, { event: 'tool_call' }>,
): DemoContentBlock[] {
  return [
    ...blocks,
    {
      type: 'tool_call',
      agent_id: event.data.agent_id ?? null,
      call_id: event.data.call_id,
      tool_name: event.data.tool_name,
      arguments: event.data.tool_arguments,
      status: 'pending',
    },
  ];
}

function applyToolResult(
  blocks: DemoContentBlock[],
  event: Extract<StreamEvent, { event: 'tool_result' }>,
): DemoContentBlock[] {
  return blocks.map((block) => {
    if (block.type !== 'tool_call' || block.call_id !== event.data.call_id) return block;
    return {
      ...block,
      agent_id: block.agent_id ?? event.data.agent_id ?? null,
      status: event.data.tool_status,
      output_preview: event.data.tool_output,
      output_truncated: event.data.tool_output_truncated,
      error_code: event.data.error_code,
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
        agent_id: event.data.agent_id ?? null,
        language: (event.data.metadata?.language as string) || 'text',
        code: '',
      };
    } else if (event.data.block_type === 'workflow') {
      next[event.data.block_index] = {
        type: 'workflow',
        agent_id: event.data.agent_id ?? null,
        last_run_id: (event.data.metadata?.last_run_id as string) || null,
        name: (event.data.metadata?.name as string) || null,
        path: (event.data.metadata?.path as string) || undefined,
        format: event.data.metadata?.format === 'json' ? 'json' : 'yaml',
        definition: {},
        raw_definition: '',
        nodes: [],
        edges: [],
        validation_status:
          event.data.metadata?.validation_status === 'passed' ||
          event.data.metadata?.validation_status === 'failed'
            ? event.data.metadata.validation_status
            : 'unknown',
        runtime_status:
          event.data.metadata?.runtime_status === 'ready' ||
          event.data.metadata?.runtime_status === 'invalid'
            ? event.data.metadata.runtime_status
            : 'not_supported',
        dry_run_status:
          event.data.metadata?.dry_run_status === 'passed' ||
          event.data.metadata?.dry_run_status === 'failed'
            ? event.data.metadata.dry_run_status
            : 'not_supported',
        health_status:
          event.data.metadata?.health_status === 'passed' ||
          event.data.metadata?.health_status === 'failed'
            ? event.data.metadata.health_status
            : 'unknown',
        validation_errors: [],
      };
    } else if (event.data.block_type === 'file') {
      next[event.data.block_index] = {
        type: 'file',
        agent_id: event.data.agent_id ?? null,
        path: (event.data.metadata?.path as string) || null,
        artifact_kind:
          (event.data.metadata?.artifact_kind as
            | 'document'
            | 'ppt'
            | 'image'
            | 'archive'
            | 'code'
            | 'workflow'
            | 'other') || 'other',
        filename: (event.data.metadata?.filename as string) || 'artifact',
        url: (event.data.metadata?.url as string) || '',
        size: (event.data.metadata?.size as number) || 0,
        mime_type: (event.data.metadata?.mime_type as string) || 'application/octet-stream',
        preview_text: (event.data.metadata?.preview_text as string) || undefined,
        preview_truncated: (event.data.metadata?.preview_truncated as boolean) || false,
        metadata: (event.data.metadata?.metadata as Record<string, unknown>) || {},
      };
    } else {
      next[event.data.block_index] = {
        type: 'text',
        agent_id: event.data.agent_id ?? null,
        text: '',
      };
    }
    return next;
  }

  if (event.event === 'agent_switch') {
    const next = updateTaskStatuses(blocks, event);
    next.push({
      type: 'agent_switch',
      from_agent: event.data.from_agent,
      to_agent: event.data.to_agent,
      task: event.data.task ?? `${event.data.to_agent} 接手任务`,
    });
    return next;
  }

  if (event.event === 'tool_call') return applyToolCall(blocks, event);
  if (event.event === 'tool_result') return applyToolResult(blocks, event);

  if (event.event !== 'delta') return blocks;

  const next = [...blocks];
  const block = next[event.data.block_index];
  if (!block) return next;

  if (block.type === 'text' && event.data.text_delta) {
    next[event.data.block_index] = {
      ...block,
      agent_id: block.agent_id ?? event.data.agent_id ?? null,
      text: `${block.text}${event.data.text_delta}`,
    };
  }
  if (block.type === 'code' && event.data.code_delta) {
    next[event.data.block_index] = {
      ...block,
      agent_id: block.agent_id ?? event.data.agent_id ?? null,
      code: `${block.code}${event.data.code_delta}`,
    };
  }
  if (block.type === 'workflow' && (event.data.text_delta || event.data.code_delta)) {
    next[event.data.block_index] = {
      ...block,
      agent_id: block.agent_id ?? event.data.agent_id ?? null,
      raw_definition: `${block.raw_definition ?? ''}${event.data.text_delta ?? event.data.code_delta ?? ''}`,
    };
  }
  return next;
}

export const useChatStore = create<ChatState>((set) => ({
  conversations: [],
  messagesByConversation: {},
  selectedConversationId: '',
  search: '',
  highlightedMessageId: null,
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
            ? (nextVisible?.id ?? '')
            : state.selectedConversationId,
      };
    });
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
              return {
                ...message,
                status: 'done' as const,
                content: completeRunningTasks(message.content),
              };
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
        selected && remoteIds.has(selected) ? selected : (conversations[0]?.id ?? '');
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
  updateConversationLocal: (conversation) => {
    set((state) => {
      const nextConversation = conversation as DemoConversation;
      const exists = state.conversations.some((item) => item.id === conversation.id);
      const conversations = exists
        ? state.conversations.map((item) => (item.id === conversation.id ? nextConversation : item))
        : [nextConversation, ...state.conversations];
      const nextVisible = conversations.find(
        (item) => item.id !== conversation.id && !item.is_archived,
      );

      return {
        conversations,
        selectedConversationId:
          conversation.is_archived && state.selectedConversationId === conversation.id
            ? (nextVisible?.id ?? '')
            : state.selectedConversationId,
      };
    });
  },
  updateMessageLocal: (message) => {
    set((state) => ({
      messagesByConversation: {
        ...state.messagesByConversation,
        [message.conversation_id]: (
          state.messagesByConversation[message.conversation_id] ?? []
        ).map((item) => (item.id === message.id ? (message as DemoMessage) : item)),
      },
    }));
  },
  replaceMessageLocal: (oldMessageId, message) => {
    set((state) => {
      const current = state.messagesByConversation[message.conversation_id] ?? [];
      const replaced = current.some((item) => item.id === oldMessageId);
      const next = replaced
        ? current.map((item) => (item.id === oldMessageId ? (message as DemoMessage) : item))
        : [...current, message as DemoMessage];
      return {
        messagesByConversation: {
          ...state.messagesByConversation,
          [message.conversation_id]: next,
        },
      };
    });
  },
  clearChat: () =>
    set({
      conversations: [],
      messagesByConversation: {},
      selectedConversationId: '',
      search: '',
      highlightedMessageId: null,
    }),
}));
