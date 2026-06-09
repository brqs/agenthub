export const queryKeys = {
  authMe: (token: string | null) => ['auth', 'me', token ?? 'anonymous'] as const,
  agents: (userId: string | null | undefined) => ['agents', userId ?? 'anonymous'] as const,
  modelProviders: () => ['model-providers'] as const,
  modelAccounts: (userId: string | null | undefined) =>
    ['model-accounts', userId ?? 'anonymous'] as const,
  agentAssets: (userId: string | null | undefined, agentId: string | null | undefined) =>
    ['agent-assets', userId ?? 'anonymous', agentId ?? 'none'] as const,
  agentAssetHistory: (userId: string | null | undefined, agentId: string | null | undefined) =>
    ['agent-asset-history', userId ?? 'anonymous', agentId ?? 'none'] as const,
  agentAssetUsage: (userId: string | null | undefined, agentId: string | null | undefined) =>
    ['agent-asset-usage', userId ?? 'anonymous', agentId ?? 'none'] as const,
  conversations: (userId: string | null | undefined) =>
    ['conversations', userId ?? 'anonymous'] as const,
  messages: (userId: string | null | undefined, conversationId: string | null | undefined) =>
    ['messages', userId ?? 'anonymous', conversationId ?? 'none'] as const,
  orchestratorRuns: (
    userId: string | null | undefined,
    conversationId: string | null | undefined,
  ) => ['orchestrator-runs', userId ?? 'anonymous', conversationId ?? 'none'] as const,
  orchestratorRunDetail: (
    userId: string | null | undefined,
    conversationId: string | null | undefined,
    runId: string | null | undefined,
  ) =>
    [
      'orchestrator-run-detail',
      userId ?? 'anonymous',
      conversationId ?? 'none',
      runId ?? 'none',
    ] as const,
  workspaceArtifacts: (
    userId: string | null | undefined,
    conversationId: string | null | undefined,
  ) => ['workspace-artifacts', userId ?? 'anonymous', conversationId ?? 'none'] as const,
};
