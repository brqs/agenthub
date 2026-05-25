import { useState } from 'react';
import type { DemoConversation } from '@/lib/mockData';
import { useChatStore } from '@/stores/chatStore';

export interface CreateConversationInput {
  title: string;
  mode: DemoConversation['mode'];
  agentIds: string[];
}

export function useCreateConversation() {
  const [isPending, setIsPending] = useState(false);
  const createConversation = useChatStore((state) => state.createConversation);

  async function mutateAsync(input: CreateConversationInput) {
    setIsPending(true);
    try {
      await new Promise((resolve) => window.setTimeout(resolve, 120));
      return createConversation(input);
    } finally {
      setIsPending(false);
    }
  }

  return {
    mutateAsync,
    isPending,
  };
}

