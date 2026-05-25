import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { env } from '@/lib/env';
import type { Agent } from '@/lib/types';
import { useAgentStore } from '@/stores/agentStore';

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
  const agents = useAgentStore((state) => state.agents);
  const hydrateAgents = useAgentStore((state) => state.hydrateAgents);

  const query = useQuery({
    queryKey: ['agents'],
    queryFn: () => agentsAdapter.listAgents(),
    enabled: !env.useMockApi,
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
