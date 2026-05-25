import { api } from '@/lib/api';
import type {
  Conversation,
  ConversationList,
  CreateConversationRequest,
} from '@/lib/types';

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
  return data.items;
}

export async function createConversation(
  input: CreateConversationRequest,
): Promise<Conversation> {
  const { data } = await api.post<Conversation>('/api/v1/conversations', input);
  return data;
}
