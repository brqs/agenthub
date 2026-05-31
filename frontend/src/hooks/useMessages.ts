import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as messagesAdapter from '@/lib/adapters/messages';
import { queryKeys } from '@/lib/queryKeys';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';
import type { DemoMessage } from '@/lib/mockData';

interface UseMessagesResult {
  data: DemoMessage[];
  isLoading: boolean;
  error: unknown;
}

/**
 * Messages for a conversation — chatStore.messagesByConversation is the
 * render-time source of truth. We fetch via
 * TanStack Query and hydrate into chatStore so SSE/applyStreamEvent keeps
 * working unchanged.
 *
 * Note: hydration only runs on `query.data` change. To avoid clobbering an
 * in-flight stream we rely on the QueryClient `staleTime` (30s by default)
 * and do not invalidate during streaming.
 */
export function useMessages(conversationId: string | null | undefined): UseMessagesResult {
  const userId = useAuthStore((state) => state.user?.id);
  const messagesByConversation = useChatStore((state) => state.messagesByConversation);
  const hydrateMessages = useChatStore((state) => state.hydrateMessages);

  const query = useQuery({
    queryKey: queryKeys.messages(userId, conversationId),
    queryFn: () =>
      conversationId
        ? messagesAdapter.listMessages(conversationId, { limit: 50, direction: 'before' })
        : Promise.resolve({ items: [], nextCursor: null, hasMore: false }),
    enabled: Boolean(conversationId) && Boolean(userId),
  });

  useEffect(() => {
    if (conversationId && query.data) {
      // Backend cursor pagination returns most-recent batch; ensure ascending order for the UI.
      const sorted = [...query.data.items].sort((a, b) =>
        a.created_at.localeCompare(b.created_at),
      );
      hydrateMessages(conversationId, sorted);
    }
  }, [conversationId, query.data, hydrateMessages]);

  return useMemo<UseMessagesResult>(
    () => ({
      data: conversationId ? messagesByConversation[conversationId] ?? [] : [],
      isLoading: Boolean(conversationId) && query.isLoading,
      error: query.error,
    }),
    [conversationId, messagesByConversation, query.isLoading, query.error],
  );
}
