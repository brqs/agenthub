import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { env } from '@/lib/env';
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
 * Agent list — `agentStore` is the single source of truth. In API mode we
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
    enabled: !env.useMockApi && Boolean(userId),
  });

  useEffect(() => {
    if (!env.useMockApi && query.data) {
      hydrateAgents(query.data);
    }
  }, [query.data, hydrateAgents]);

  return useMemo<UseAgentsResult>(
    () => ({
      data: agents,
      isLoading: !env.useMockApi && query.isLoading,
      error: env.useMockApi ? null : query.error,
    }),
    [agents, query.isLoading, query.error],
  );
}
