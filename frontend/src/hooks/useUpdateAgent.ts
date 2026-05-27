import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { env } from '@/lib/env';
import type { Agent, UpdateAgentRequest } from '@/lib/types';
import { useAgentStore } from '@/stores/agentStore';

export function useUpdateAgent() {
  const queryClient = useQueryClient();
  const updateAgentLocal = useAgentStore((state) => state.updateAgentLocal);
  const [mockPending, setMockPending] = useState(false);

  const apiMutation = useMutation({
    mutationFn: ({ agentId, input }: { agentId: string; input: UpdateAgentRequest }) =>
      agentsAdapter.updateAgent(agentId, input),
    onSuccess: (agent: Agent) => {
      updateAgentLocal(agent);
      void queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });

  async function mutateAsync({
    agentId,
    input,
  }: {
    agentId: string;
    input: UpdateAgentRequest;
  }): Promise<Agent> {
    if (env.useMockApi) {
      setMockPending(true);
      try {
        await new Promise((resolve) => window.setTimeout(resolve, 120));
        const current = useAgentStore.getState().agents.find((agent) => agent.id === agentId);
        if (!current) throw new Error('Agent not found');
        const updated: Agent = {
          ...current,
          ...input,
          capabilities: input.capabilities ?? current.capabilities,
          avatar_url: input.avatar_url ?? current.avatar_url,
          config: input.config ?? current.config,
          system_prompt:
            input.system_prompt === undefined ? current.system_prompt : input.system_prompt,
        };
        updateAgentLocal(updated);
        return updated;
      } finally {
        setMockPending(false);
      }
    }

    return apiMutation.mutateAsync({ agentId, input });
  }

  return {
    mutateAsync,
    isPending: env.useMockApi ? mockPending : apiMutation.isPending,
  };
}
