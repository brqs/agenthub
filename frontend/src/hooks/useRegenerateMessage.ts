import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as messagesAdapter from '@/lib/adapters/messages';
import type { DemoMessage } from '@/lib/mockData';
import type { Message } from '@/lib/types';
import { useChatStore } from '@/stores/chatStore';

export function useRegenerateMessage() {
  const queryClient = useQueryClient();
  const replaceMessageLocal = useChatStore((state) => state.replaceMessageLocal);

  const mutation = useMutation({
    mutationFn: (messageId: string) => messagesAdapter.regenerateMessage(messageId),
  });

  async function regenerate(message: DemoMessage): Promise<DemoMessage | Message> {
    const regenerated = await mutation.mutateAsync(message.id);
    replaceMessageLocal(message.id, regenerated);
    void queryClient.invalidateQueries({ queryKey: ['messages', regenerated.conversation_id] });
    return regenerated;
  }

  return {
    regenerate,
    isPending: mutation.isPending,
  };
}
