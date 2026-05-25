import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as conversationsAdapter from '@/lib/adapters/conversations';
import { env } from '@/lib/env';
import type { Conversation } from '@/lib/types';
import { useChatStore } from '@/stores/chatStore';

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
export function useConversations(): UseConversationsResult {
  const conversations = useChatStore((state) => state.conversations);
  const hydrate = useChatStore((state) => state.hydrateConversations);

  const query = useQuery({
    queryKey: ['conversations'],
    queryFn: () => conversationsAdapter.listConversations(),
    enabled: !env.useMockApi,
  });

  useEffect(() => {
    if (!env.useMockApi && query.data) {
      hydrate(query.data);
    }
  }, [query.data, hydrate]);

  return useMemo<UseConversationsResult>(
    () => ({
      data: conversations,
      isLoading: !env.useMockApi && query.isLoading,
      error: env.useMockApi ? null : query.error,
    }),
    [conversations, query.isLoading, query.error],
  );
}
