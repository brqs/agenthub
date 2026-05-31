export const queryKeys = {
  authMe: (token: string | null) => ['auth', 'me', token ?? 'anonymous'] as const,
  agents: (userId: string | null | undefined) => ['agents', userId ?? 'anonymous'] as const,
  conversations: (userId: string | null | undefined) =>
    ['conversations', userId ?? 'anonymous'] as const,
  messages: (userId: string | null | undefined, conversationId: string | null | undefined) =>
    ['messages', userId ?? 'anonymous', conversationId ?? 'none'] as const,
};
