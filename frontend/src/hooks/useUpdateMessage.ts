import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as messagesAdapter from '@/lib/adapters/messages';
import { env } from '@/lib/env';
import type { Message, UpdateMessageRequest } from '@/lib/types';
import { useChatStore } from '@/stores/chatStore';

export function useUpdateMessage() {
  const queryClient = useQueryClient();
  const toggleMessagePin = useChatStore((state) => state.toggleMessagePin);
  const updateMessageLocal = useChatStore((state) => state.updateMessageLocal);

  const mutation = useMutation({
    mutationFn: ({ messageId, input }: { messageId: string; input: UpdateMessageRequest }) =>
      messagesAdapter.updateMessage(messageId, input),
    onSuccess: (message) => {
      updateMessageLocal(message);
      void queryClient.invalidateQueries({ queryKey: ['messages', message.conversation_id] });
    },
  });

  async function update(
    message: Pick<Message, 'id' | 'is_pinned'>,
    input: UpdateMessageRequest,
  ): Promise<Message | null> {
    if (env.useMockApi) {
      if (input.is_pinned !== undefined) toggleMessagePin(message.id);
      return null;
    }
    return mutation.mutateAsync({ messageId: message.id, input });
  }

  return {
    update,
    isPending: mutation.isPending,
  };
}
