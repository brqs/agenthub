import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as conversationsAdapter from '@/lib/adapters/conversations';
import { queryKeys } from '@/lib/queryKeys';
import type { Conversation } from '@/lib/types';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';
import type { ListConversationsParams } from '@/lib/adapters/conversations';

interface UseConversationsResult {
  data: Conversation[];
  isLoading: boolean;
  error: unknown;
}

/**
 * Conversations list — single source of truth is `chatStore.conversations`.
 *
 * TanStack Query fetches once and hydrates into chatStore; downstream
 *   streaming/send mutations keep updating the store, so the UI shape is identical.
 */
export function useConversations(params: ListConversationsParams = {}): UseConversationsResult {
  const userId = useAuthStore((state) => state.user?.id);
  const conversations = useChatStore((state) => state.conversations);
  const hydrate = useChatStore((state) => state.hydrateConversations);
  const queryParams = useMemo(
    () => ({
      archived: params.archived ?? false,
      pinnedOnly: params.pinnedOnly,
      search: params.search,
      page: params.page,
      pageSize: params.pageSize,
    }),
    [params.archived, params.pinnedOnly, params.search, params.page, params.pageSize],
  );

  const query = useQuery({
    queryKey: [...queryKeys.conversations(userId), queryParams],
    queryFn: () => conversationsAdapter.listConversations(queryParams),
    enabled: Boolean(userId),
  });

  useEffect(() => {
    if (query.data && !queryParams.archived) {
      hydrate(query.data);
    }
  }, [query.data, hydrate, queryParams.archived]);

  const shouldUseHydratedStore =
    !queryParams.archived && !queryParams.pinnedOnly && !queryParams.search && !queryParams.page;

  const localData = useMemo(() => {
    if (!shouldUseHydratedStore) return query.data ?? [];
    return conversations.filter((conversation) => {
      if (!queryParams.archived && conversation.is_archived) return false;
      if (queryParams.pinnedOnly && !conversation.is_pinned) return false;
      if (
        queryParams.search &&
        !conversation.title.toLowerCase().includes(queryParams.search.toLowerCase())
      ) {
        return false;
      }
      return true;
    });
  }, [
    conversations,
    query.data,
    queryParams.archived,
    queryParams.pinnedOnly,
    queryParams.search,
    shouldUseHydratedStore,
  ]);

  return useMemo<UseConversationsResult>(
    () => ({
      data: query.data ? localData : [],
      isLoading: query.isLoading,
      error: query.error,
    }),
    [localData, query.data, query.isLoading, query.error],
  );
}
