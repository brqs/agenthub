import { create } from 'zustand';
import {
  createMockReply,
  mockConversations,
  mockMessages,
  type DemoContentBlock,
  type DemoConversation,
  type DemoMessage,
} from '@/lib/mockData';
import type { StreamEvent } from '@/lib/types';

interface ChatState {
  conversations: DemoConversation[];
  messagesByConversation: Record<string, DemoMessage[]>;
  selectedConversationId: string;
  search: string;
  createConversation: (input: {
    title: string;
    mode: DemoConversation['mode'];
    agentIds: string[];
  }) => DemoConversation;
  setSelectedConversationId: (conversationId: string) => void;
  setSearch: (search: string) => void;
  createPendingExchange: (conversationId: string, text: string) => { agentMessageId: string } | null;
  applyStreamEvent: (messageId: string, event: StreamEvent) => void;
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

function applyDelta(blocks: DemoContentBlock[], event: StreamEvent): DemoContentBlock[] {
  if (event.event === 'block_start') {
    const next = [...blocks];
    if (event.data.block_type === 'code') {
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
              return { ...message, status: 'done' as const };
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
}));
