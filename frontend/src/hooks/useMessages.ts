import { useCallback, useEffect, useMemo } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import * as messagesAdapter from '@/lib/adapters/messages';
import { queryKeys } from '@/lib/queryKeys';
import { useAuthStore } from '@/stores/authStore';
import { sortMessagesForDisplay, useChatStore } from '@/stores/chatStore';
import type { DemoMessage } from '@/lib/mockData';

interface UseMessagesResult {
  data: DemoMessage[];
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  fetchPreviousPage: () => void;
  error: unknown;
}

const DEFAULT_MESSAGE_PAGE_SIZE = 30;

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

  const query = useInfiniteQuery({
    queryKey: queryKeys.messages(userId, conversationId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      conversationId
        ? messagesAdapter.listMessages(conversationId, {
            limit: DEFAULT_MESSAGE_PAGE_SIZE,
            direction: 'before',
            cursor: pageParam ?? undefined,
          })
        : Promise.resolve({ items: [], nextCursor: null, hasMore: false }),
    getNextPageParam: (lastPage) => (lastPage.hasMore ? lastPage.nextCursor : undefined),
    enabled: Boolean(conversationId) && Boolean(userId),
  });
  const {
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
  } = query;

  useEffect(() => {
    if (conversationId && query.data) {
      const sorted = [...query.data.pages]
        .reverse()
        .flatMap((page) => page.items)
        .sort((a, b) => a.created_at.localeCompare(b.created_at));
      hydrateMessages(conversationId, sortMessagesForDisplay(sorted));
    }
  }, [conversationId, query.data, hydrateMessages]);

  const fetchPreviousPage = useCallback(() => {
    if (!hasNextPage || isFetchingNextPage) return;
    void fetchNextPage();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage]);

  return useMemo<UseMessagesResult>(
    () => ({
      data: conversationId ? messagesByConversation[conversationId] ?? [] : [],
      isLoading: Boolean(conversationId) && isLoading,
      isLoadingMore: isFetchingNextPage,
      hasMore: Boolean(hasNextPage),
      fetchPreviousPage,
      error,
    }),
    [
      conversationId,
      error,
      fetchPreviousPage,
      hasNextPage,
      isFetchingNextPage,
      isLoading,
      messagesByConversation,
    ],
  );
}
