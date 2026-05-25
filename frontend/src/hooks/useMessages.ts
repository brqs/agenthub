import { useMemo } from 'react';
import { useChatStore } from '@/stores/chatStore';

export function useMessages(conversationId: string | null | undefined) {
  const messagesByConversation = useChatStore((state) => state.messagesByConversation);

  return useMemo(
    () => ({
      data: conversationId ? messagesByConversation[conversationId] ?? [] : [],
      isLoading: false,
      error: null,
    }),
    [conversationId, messagesByConversation],
  );
}

