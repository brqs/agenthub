import { create } from 'zustand';
import {
  createMockReply,
  mockConversations,
  mockMessages,
  type DemoContentBlock,
  type DemoConversation,
  type DemoMessage,
} from '@/lib/mockData';

interface ChatState {
  conversations: DemoConversation[];
  messagesByConversation: Record<string, DemoMessage[]>;
  selectedConversationId: string;
  search: string;
  setSelectedConversationId: (conversationId: string) => void;
  setSearch: (search: string) => void;
  sendMockMessage: (conversationId: string, text: string) => void;
}

const STREAM_REPLY =
  '收到。我会先用 Mock 数据把桌面端体验跑顺：四栏布局、Agent 右侧栏、消息气泡和流式回复都会保留真实 API 的接入位置。';

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

function getTargetAgent(conversation: DemoConversation): string {
  if (conversation.mode === 'group') {
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

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: mockConversations,
  messagesByConversation: mockMessages,
  selectedConversationId: mockConversations[0]?.id ?? '',
  search: '',
  setSelectedConversationId: (conversationId) => set({ selectedConversationId: conversationId }),
  setSearch: (search) => set({ search }),
  sendMockMessage: (conversationId, text) => {
    const conversation = get().conversations.find((item) => item.id === conversationId);
    if (!conversation) return;

    const userMessage = createUserMessage(conversationId, text);
    const agentId = getTargetAgent(conversation);
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

    let cursor = 0;
    const timer = window.setInterval(() => {
      const next = STREAM_REPLY.slice(cursor, cursor + 2);
      cursor += 2;

      set((state) => {
        const messages = state.messagesByConversation[conversationId] ?? [];
        return {
          messagesByConversation: {
            ...state.messagesByConversation,
            [conversationId]: messages.map((message) =>
              message.id === reply.id
                ? {
                    ...message,
                    status: cursor >= STREAM_REPLY.length ? 'done' : 'streaming',
                    content: appendText(message.content, next),
                  }
                : message,
            ),
          },
        };
      });

      if (cursor >= STREAM_REPLY.length) {
        window.clearInterval(timer);
      }
    }, 35);
  },
}));

