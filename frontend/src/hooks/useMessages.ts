import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as messagesAdapter from '@/lib/adapters/messages';
import { env } from '@/lib/env';
import { useChatStore } from '@/stores/chatStore';
import type { DemoMessage } from '@/lib/mockData';

interface UseMessagesResult {
  data: DemoMessage[];
  isLoading: boolean;
  error: unknown;
}

/**
 * Messages for a conversation — chatStore.messagesByConversation is the
 * render-time source of truth in both modes. In API mode we fetch via
 * TanStack Query and hydrate into chatStore so SSE/applyStreamEvent keeps
 * working unchanged.
 *
 * Note: hydration only runs on `query.data` change. To avoid clobbering an
 * in-flight stream we rely on the QueryClient `staleTime` (30s by default)
 * and do not invalidate during streaming.
 */
export function useMessages(conversationId: string | null | undefined): UseMessagesResult {
  const messagesByConversation = useChatStore((state) => state.messagesByConversation);
  const hydrateMessages = useChatStore((state) => state.hydrateMessages);

  const query = useQuery({
    queryKey: ['messages', conversationId],
    queryFn: () =>
      conversationId
        ? messagesAdapter.listMessages(conversationId, { limit: 50, direction: 'before' })
        : Promise.resolve({ items: [], nextCursor: null, hasMore: false }),
    enabled: Boolean(conversationId) && !env.useMockApi,
  });

  useEffect(() => {
    if (!env.useMockApi && conversationId && query.data) {
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
      isLoading: !env.useMockApi && Boolean(conversationId) && query.isLoading,
      error: env.useMockApi ? null : query.error,
    }),
    [conversationId, messagesByConversation, query.isLoading, query.error],
  );
}
