import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import type { Agent, UpdateAgentRequest } from '@/lib/types';
import { useAgentStore } from '@/stores/agentStore';

export function useUpdateAgent() {
  const queryClient = useQueryClient();
  const updateAgentLocal = useAgentStore((state) => state.updateAgentLocal);

  const apiMutation = useMutation({
    mutationFn: ({ agentId, input }: { agentId: string; input: UpdateAgentRequest }) =>
      agentsAdapter.updateAgent(agentId, input),
    onSuccess: (agent: Agent) => {
      updateAgentLocal(agent);
      void queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });

  return {
    mutateAsync: ({
      agentId,
      input,
    }: {
      agentId: string;
      input: UpdateAgentRequest;
    }): Promise<Agent> => apiMutation.mutateAsync({ agentId, input }),
    isPending: apiMutation.isPending,
  };
}
