import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as messagesAdapter from '@/lib/adapters/messages';
import { env } from '@/lib/env';
import type { DemoMessage } from '@/lib/mockData';
import type { Message } from '@/lib/types';
import { useChatStore } from '@/stores/chatStore';

export function useRegenerateMessage() {
  const queryClient = useQueryClient();
  const resetMessageForRetry = useChatStore((state) => state.resetMessageForRetry);
  const replaceMessageLocal = useChatStore((state) => state.replaceMessageLocal);

  const mutation = useMutation({
    mutationFn: (messageId: string) => messagesAdapter.regenerateMessage(messageId),
  });

  async function regenerate(message: DemoMessage): Promise<DemoMessage | Message> {
    if (env.useMockApi) {
      resetMessageForRetry(message.id);
      return { ...message, status: 'streaming', content: [{ type: 'text', text: '' }] };
    }
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
