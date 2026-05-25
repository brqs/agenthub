import { useMemo } from 'react';
import { useChatStore } from '@/stores/chatStore';

export function useConversations() {
  const conversations = useChatStore((state) => state.conversations);

  return useMemo(
    () => ({
      data: conversations,
      isLoading: false,
      error: null,
    }),
    [conversations],
  );
}

