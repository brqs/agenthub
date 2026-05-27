import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as conversationsAdapter from '@/lib/adapters/conversations';
import { env } from '@/lib/env';
import type { Conversation } from '@/lib/types';
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
 * - Mock mode: chatStore is seeded with mockConversations and mutated locally.
 * - API mode: TanStack Query fetches once and hydrates into chatStore; downstream
 *   streaming/send mutations keep updating the store, so the UI shape is identical.
 */
export function useConversations(params: ListConversationsParams = {}): UseConversationsResult {
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
    queryKey: ['conversations', queryParams],
    queryFn: () => conversationsAdapter.listConversations(queryParams),
    enabled: !env.useMockApi,
  });

  useEffect(() => {
    if (!env.useMockApi && query.data && !queryParams.archived) {
      hydrate(query.data);
    }
  }, [query.data, hydrate, queryParams.archived]);

  return useMemo<UseConversationsResult>(
    () => ({
      data: env.useMockApi ? conversations : query.data ?? [],
      isLoading: !env.useMockApi && query.isLoading,
      error: env.useMockApi ? null : query.error,
    }),
    [conversations, query.data, query.isLoading, query.error],
  );
}
