import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as conversationsAdapter from '@/lib/adapters/conversations';
import { env } from '@/lib/env';
import type { Conversation, UpdateConversationRequest } from '@/lib/types';
import { useChatStore } from '@/stores/chatStore';
import type { ListConversationsParams } from '@/lib/adapters/conversations';

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
      syncConversationQueries(queryClient, conversation);
      void queryClient.invalidateQueries({ queryKey: ['conversations'], exact: false });
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

function syncConversationQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  conversation: Conversation,
) {
  const queries = queryClient.getQueryCache().findAll({ queryKey: ['conversations'] });
  queries.forEach((query) => {
    const [, params] = query.queryKey as ['conversations', ListConversationsParams | undefined];
    queryClient.setQueryData<Conversation[]>(
      query.queryKey,
      (current) => reconcileConversationList(current, conversation, params),
    );
  });
}

export function reconcileConversationList(
  current: Conversation[] | undefined,
  conversation: Conversation,
  params: ListConversationsParams = {},
): Conversation[] | undefined {
  if (!current) return current;
  const matches = matchesConversationParams(conversation, params);
  const exists = current.some((item) => item.id === conversation.id);

  if (!matches) {
    return current.filter((item) => item.id !== conversation.id);
  }

  if (exists) {
    return current.map((item) => (item.id === conversation.id ? conversation : item));
  }

  return [conversation, ...current];
}

function matchesConversationParams(
  conversation: Conversation,
  params: ListConversationsParams = {},
): boolean {
  const archived = params.archived ?? false;
  if (conversation.is_archived !== archived) return false;
  if (params.pinnedOnly && !conversation.is_pinned) return false;
  if (params.search && !conversation.title.toLowerCase().includes(params.search.toLowerCase())) {
    return false;
  }
  return true;
}
