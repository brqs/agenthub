import { api } from '@/lib/api';
import type {
  Message,
  MessageList,
  InterruptMessageResponse,
  QueueMessageRequest,
  QueueMessageResponse,
  SendMessageRequest,
  SendMessageResponse,
  UpdateQueuedMessageRequest,
  UpdateMessageRequest,
} from '@/lib/types';
import { normalizeMessage } from './normalizers';

export type SendMessageWithAttachments = SendMessageRequest & { attachment_ids?: string[] };
export type QueueMessageWithAttachments = QueueMessageRequest & { attachment_ids?: string[] };

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

export async function queueMessage(
  conversationId: string,
  input: QueueMessageRequest,
): Promise<QueueMessageResponse> {
  const { data } = await api.post<QueueMessageResponse>(
    `/api/v1/conversations/${conversationId}/queued-messages`,
    input,
  );
  return {
    ...data,
    queued_message: normalizeMessage(data.queued_message),
  };
}

export async function updateQueuedMessage(
  messageId: string,
  input: UpdateQueuedMessageRequest,
): Promise<QueueMessageResponse> {
  const { data } = await api.patch<QueueMessageResponse>(
    `/api/v1/queued-messages/${messageId}`,
    input,
  );
  return {
    ...data,
    queued_message: normalizeMessage(data.queued_message),
  };
}

export async function deleteQueuedMessage(messageId: string): Promise<void> {
  await api.delete(`/api/v1/queued-messages/${messageId}`);
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

export async function interruptMessage(messageId: string): Promise<InterruptMessageResponse> {
  const { data } = await api.post<InterruptMessageResponse>(
    `/api/v1/messages/${messageId}/interrupt`,
  );
  return {
    ...data,
    message: normalizeMessage(data.message),
  };
}
