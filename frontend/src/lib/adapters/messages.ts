import { api } from '@/lib/api';
import type {
  Message,
  MessageList,
  SendMessageRequest,
  SendMessageResponse,
} from '@/lib/types';

export interface ListMessagesParams {
  cursor?: string;
  limit?: number;
  direction?: 'before' | 'after';
}

export async function listMessages(
  conversationId: string,
  params: ListMessagesParams = {},
): Promise<{ items: Message[]; nextCursor: string | null; hasMore: boolean }> {
  const { data } = await api.get<MessageList>(
    `/api/v1/conversations/${conversationId}/messages`,
    {
      params: {
        cursor: params.cursor,
        limit: params.limit,
        direction: params.direction,
      },
    },
  );
  return {
    items: data.items,
    nextCursor: data.next_cursor ?? null,
    hasMore: Boolean(data.has_more),
  };
}

export async function sendMessage(
  conversationId: string,
  input: SendMessageRequest,
): Promise<SendMessageResponse> {
  const { data } = await api.post<SendMessageResponse>(
    `/api/v1/conversations/${conversationId}/messages`,
    input,
  );
  return data;
}

export async function regenerateMessage(messageId: string): Promise<Message> {
  const { data } = await api.post<Message>(`/api/v1/messages/${messageId}/regenerate`);
  return data;
}
