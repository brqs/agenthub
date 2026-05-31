import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as conversationsAdapter from '@/lib/adapters/conversations';
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
  const addConversation = useChatStore((state) => state.addConversation);

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

  return {
    mutateAsync: (input: CreateConversationInput): Promise<Conversation> =>
      apiMutation.mutateAsync(input),
    isPending: apiMutation.isPending,
  };
}
