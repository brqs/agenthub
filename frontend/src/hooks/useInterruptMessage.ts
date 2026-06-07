import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as messagesAdapter from '@/lib/adapters/messages';
import { queryKeys } from '@/lib/queryKeys';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

export function useInterruptMessage() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);
  const updateMessageLocal = useChatStore((state) => state.updateMessageLocal);
  const finishActiveStream = useChatStore((state) => state.finishActiveStream);
  const setActiveStreamInterrupting = useChatStore(
    (state) => state.setActiveStreamInterrupting,
  );

  const mutation = useMutation({
    mutationFn: (messageId: string) => messagesAdapter.interruptMessage(messageId),
  });

  async function interrupt(messageId: string) {
    setActiveStreamInterrupting(messageId, true);
    let keepInterrupting = false;
    try {
      const response = await mutation.mutateAsync(messageId);
      updateMessageLocal(response.message);
      if (response.state !== 'interrupting') {
        finishActiveStream(messageId);
      } else {
        keepInterrupting = true;
      }
      void queryClient.invalidateQueries({
        queryKey: queryKeys.messages(userId, response.message.conversation_id),
      });
      return response;
    } finally {
      if (!keepInterrupting) {
        setActiveStreamInterrupting(messageId, false);
      }
    }
  }

  return {
    interrupt,
    isPending: mutation.isPending,
  };
}
