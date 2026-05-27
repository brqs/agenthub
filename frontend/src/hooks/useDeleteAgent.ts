import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { env } from '@/lib/env';
import { useAgentStore } from '@/stores/agentStore';

export function useDeleteAgent() {
  const queryClient = useQueryClient();
  const removeAgentLocal = useAgentStore((state) => state.removeAgentLocal);
  const [mockPending, setMockPending] = useState(false);

  const apiMutation = useMutation({
    mutationFn: (agentId: string) => agentsAdapter.deleteAgent(agentId),
    onSuccess: (_data, agentId) => {
      removeAgentLocal(agentId);
      void queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });

  async function mutateAsync(agentId: string): Promise<void> {
    if (env.useMockApi) {
      setMockPending(true);
      try {
        await new Promise((resolve) => window.setTimeout(resolve, 120));
        removeAgentLocal(agentId);
        return;
      } finally {
        setMockPending(false);
      }
    }

    return apiMutation.mutateAsync(agentId);
  }

  return {
    mutateAsync,
    isPending: env.useMockApi ? mockPending : apiMutation.isPending,
  };
}
