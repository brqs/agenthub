import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { useAgentStore } from '@/stores/agentStore';

export function useDeleteAgent() {
  const queryClient = useQueryClient();
  const removeAgentLocal = useAgentStore((state) => state.removeAgentLocal);

  const apiMutation = useMutation({
    mutationFn: (agentId: string) => agentsAdapter.deleteAgent(agentId),
    onSuccess: (_data, agentId) => {
      removeAgentLocal(agentId);
      void queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });

  return {
    mutateAsync: (agentId: string): Promise<void> => apiMutation.mutateAsync(agentId),
    isPending: apiMutation.isPending,
  };
}
