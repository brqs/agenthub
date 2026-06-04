import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as orchestratorRunsAdapter from '@/lib/adapters/orchestratorRuns';
import { queryKeys } from '@/lib/queryKeys';
import { useAuthStore } from '@/stores/authStore';

export function useOrchestratorRunForMessage(
  conversationId: string | null | undefined,
  messageId: string | null | undefined,
  enabled = true,
) {
  const userId = useAuthStore((state) => state.user?.id);
  const runsQuery = useQuery({
    queryKey: queryKeys.orchestratorRuns(userId, conversationId),
    queryFn: () => orchestratorRunsAdapter.listOrchestratorRuns(conversationId as string),
    enabled: enabled && Boolean(userId) && Boolean(conversationId) && Boolean(messageId),
    retry: false,
    staleTime: 30_000,
  });

  const runId = useMemo(() => {
    const runs = runsQuery.data?.items ?? [];
    return runs.find((run) => run.agent_message_id === messageId)?.id ?? null;
  }, [messageId, runsQuery.data?.items]);

  return useQuery({
    queryKey: queryKeys.orchestratorRunDetail(userId, conversationId, runId),
    queryFn: () =>
      orchestratorRunsAdapter.getOrchestratorRunDetail(conversationId as string, runId as string),
    enabled: enabled && Boolean(userId) && Boolean(conversationId) && Boolean(runId),
    retry: false,
    staleTime: 30_000,
  });
}
