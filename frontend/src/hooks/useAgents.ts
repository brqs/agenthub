import { useMemo } from 'react';
import { useAgentStore } from '@/stores/agentStore';

export function useAgents() {
  const agents = useAgentStore((state) => state.agents);

  return useMemo(
    () => ({
      data: agents,
      isLoading: false,
      error: null,
    }),
    [agents],
  );
}
