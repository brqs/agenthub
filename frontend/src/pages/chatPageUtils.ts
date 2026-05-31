import type { Conversation } from '@/lib/types';

export function resolveConversation(
  conversations: Conversation[],
  routeConversationId: string | undefined,
  selectedConversationId: string,
): Conversation | undefined {
  const activeConversationId = routeConversationId ?? selectedConversationId;
  const activeConversation = conversations.find((item) => item.id === activeConversationId);
  if (activeConversation || routeConversationId) return activeConversation;
  return conversations[0];
}
