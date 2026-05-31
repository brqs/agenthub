import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { queryKeys } from '@/lib/queryKeys';
import type { Agent } from '@/lib/types';
import { useAgentStore } from '@/stores/agentStore';
import { useAuthStore } from '@/stores/authStore';

interface UseAgentsResult {
  data: Agent[];
  isLoading: boolean;
  error: unknown;
}

/**
 * Agent list — `agentStore` is the single source of truth. We
 * fetch via TanStack Query and hydrate the store so create/update mutations
 * keep working uniformly against the same render path.
 */
export function useAgents(): UseAgentsResult {
  const userId = useAuthStore((state) => state.user?.id);
  const agents = useAgentStore((state) => state.agents);
  const hydrateAgents = useAgentStore((state) => state.hydrateAgents);

  const query = useQuery({
    queryKey: queryKeys.agents(userId),
    queryFn: () => agentsAdapter.listAgents(),
    enabled: Boolean(userId),
  });

  useEffect(() => {
    if (query.data) {
      hydrateAgents(query.data);
    }
  }, [query.data, hydrateAgents]);

  return useMemo<UseAgentsResult>(
    () => ({
      data: agents,
      isLoading: query.isLoading,
      error: query.error,
    }),
    [agents, query.isLoading, query.error],
  );
}
