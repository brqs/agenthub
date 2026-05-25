import { useState } from 'react';
import { useChatStore } from '@/stores/chatStore';

export function useSendMessage() {
  const [isPending, setIsPending] = useState(false);
  const createPendingExchange = useChatStore((state) => state.createPendingExchange);

  async function sendMessage(conversationId: string, text: string) {
    setIsPending(true);
    try {
      await new Promise((resolve) => window.setTimeout(resolve, 120));
      return createPendingExchange(conversationId, text);
    } finally {
      setIsPending(false);
    }
  }

  return {
    sendMessage,
    isPending,
  };
}

