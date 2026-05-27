import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as conversationsAdapter from '@/lib/adapters/conversations';
import { env } from '@/lib/env';
import type { Conversation, UpdateConversationRequest } from '@/lib/types';
import { useChatStore } from '@/stores/chatStore';

export function useUpdateConversation() {
  const queryClient = useQueryClient();
  const conversations = useChatStore((state) => state.conversations);
  const toggleConversationPin = useChatStore((state) => state.toggleConversationPin);
  const toggleConversationArchive = useChatStore((state) => state.toggleConversationArchive);
  const updateConversationLocal = useChatStore((state) => state.updateConversationLocal);

  const mutation = useMutation({
    mutationFn: ({
      conversationId,
      input,
    }: {
      conversationId: string;
      input: UpdateConversationRequest;
    }) => conversationsAdapter.updateConversation(conversationId, input),
    onSuccess: (conversation) => {
      updateConversationLocal(conversation);
      void queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });

  async function update(
    conversationId: string,
    input: UpdateConversationRequest,
  ): Promise<Conversation | null> {
    if (env.useMockApi) {
      if (input.is_pinned !== undefined) toggleConversationPin(conversationId);
      if (input.is_archived !== undefined) toggleConversationArchive(conversationId);
      return conversations.find((item) => item.id === conversationId) ?? null;
    }
    return mutation.mutateAsync({ conversationId, input });
  }

  return {
    update,
    isPending: mutation.isPending,
  };
}
