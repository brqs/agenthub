import { api } from '@/lib/api';
import type {
  Conversation,
  ConversationList,
  CreateConversationRequest,
  UpdateConversationRequest,
} from '@/lib/types';
import { normalizeConversation } from './normalizers';

export interface ListConversationsParams {
  archived?: boolean;
  pinnedOnly?: boolean;
  search?: string;
  page?: number;
  pageSize?: number;
}

export async function listConversations(
  params: ListConversationsParams = {},
): Promise<Conversation[]> {
  const { data } = await api.get<ConversationList>('/api/v1/conversations', {
    params: {
      archived: params.archived,
      pinned_only: params.pinnedOnly,
      search: params.search,
      page: params.page,
      page_size: params.pageSize,
    },
  });
  return data.items.map(normalizeConversation);
}

export async function createConversation(
  input: CreateConversationRequest,
): Promise<Conversation> {
  const { data } = await api.post<Conversation>('/api/v1/conversations', input);
  return normalizeConversation(data);
}

export async function updateConversation(
  conversationId: string,
  input: UpdateConversationRequest,
): Promise<Conversation> {
  const { data } = await api.patch<Conversation>(
    `/api/v1/conversations/${conversationId}`,
    input,
  );
  return normalizeConversation(data);
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await api.delete(`/api/v1/conversations/${conversationId}`);
}
