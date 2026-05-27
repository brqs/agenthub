import { api } from '@/lib/api';
import type {
  Message,
  MessageList,
  SendMessageRequest,
  SendMessageResponse,
  UpdateMessageRequest,
} from '@/lib/types';
import { normalizeMessage } from './normalizers';

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
    items: data.items.map(normalizeMessage),
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
  return {
    user_message: normalizeMessage(data.user_message),
    agent_message: normalizeMessage(data.agent_message),
  };
}

export async function updateMessage(
  messageId: string,
  input: UpdateMessageRequest,
): Promise<Message> {
  const { data } = await api.patch<Message>(`/api/v1/messages/${messageId}`, input);
  return normalizeMessage(data);
}

export async function deleteMessage(messageId: string): Promise<void> {
  await api.delete(`/api/v1/messages/${messageId}`);
}

export async function regenerateMessage(messageId: string): Promise<Message> {
  const { data } = await api.post<Message>(`/api/v1/messages/${messageId}/regenerate`);
  return normalizeMessage(data);
}
