import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as conversationsAdapter from '@/lib/adapters/conversations';
import { env } from '@/lib/env';
import { queryKeys } from '@/lib/queryKeys';
import type { Conversation } from '@/lib/types';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

export interface CreateConversationInput {
  title: string;
  mode: 'single' | 'group';
  agentIds: string[];
}

export function useCreateConversation() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);
  const createMockConversation = useChatStore((state) => state.createConversation);
  const addConversation = useChatStore((state) => state.addConversation);
  const [mockPending, setMockPending] = useState(false);

  const apiMutation = useMutation({
    mutationFn: (input: CreateConversationInput) =>
      conversationsAdapter.createConversation({
        title: input.title,
        mode: input.mode,
        agent_ids: input.agentIds,
      }),
    onSuccess: (created) => {
      addConversation(created);
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations(userId) });
    },
  });

  async function mutateAsync(input: CreateConversationInput): Promise<Conversation> {
    if (env.useMockApi) {
      setMockPending(true);
      try {
        await new Promise((resolve) => window.setTimeout(resolve, 120));
        return createMockConversation(input);
      } finally {
        setMockPending(false);
      }
    }
    return apiMutation.mutateAsync(input);
  }

  return {
    mutateAsync,
    isPending: env.useMockApi ? mockPending : apiMutation.isPending,
  };
}
