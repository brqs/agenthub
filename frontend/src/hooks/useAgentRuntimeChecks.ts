import { useMutation } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';

export function useAgentMcpHealthCheck() {
  const mutation = useMutation({
    mutationFn: (agentId: string) => agentsAdapter.checkAgentMcpHealth(agentId),
  });

  return {
    mutateAsync: mutation.mutateAsync,
    data: mutation.data,
    error: mutation.error,
    isPending: mutation.isPending,
  };
}

export function useAgentTestRun() {
  const mutation = useMutation({
    mutationFn: ({ agentId, prompt }: { agentId: string; prompt: string }) =>
      agentsAdapter.testRunAgent(agentId, prompt),
  });

  return {
    mutateAsync: mutation.mutateAsync,
    data: mutation.data,
    error: mutation.error,
    isPending: mutation.isPending,
  };
}
