import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { queryKeys } from '@/lib/queryKeys';
import type { AgentKnowledgeUsage } from '@/lib/types';
import { useAgentStore } from '@/stores/agentStore';
import { useAuthStore } from '@/stores/authStore';

async function refreshAgent(agentId: string) {
  const agents = await agentsAdapter.listAgents();
  return agents.find((agent) => agent.id === agentId) ?? null;
}

export function useAgentAssets() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);
  const updateAgentLocal = useAgentStore((state) => state.updateAgentLocal);

  async function syncAgent(agentId: string) {
    const agent = await refreshAgent(agentId);
    if (agent) updateAgentLocal(agent);
    void queryClient.invalidateQueries({ queryKey: queryKeys.agents(userId) });
  }

  const uploadKnowledge = useMutation({
    mutationFn: (input: {
      agentId: string;
      file: File;
      label?: string;
      usage?: AgentKnowledgeUsage;
    }) => agentsAdapter.uploadAgentKnowledge(input),
    onSuccess: async (_asset, input) => syncAgent(input.agentId),
  });

  const deleteKnowledge = useMutation({
    mutationFn: (input: { agentId: string; uploadId: string }) =>
      agentsAdapter.deleteAgentKnowledge(input.agentId, input.uploadId),
    onSuccess: async (_asset, input) => syncAgent(input.agentId),
  });

  const uploadSkill = useMutation({
    mutationFn: (input: { agentId: string; file: File; name?: string; description?: string }) =>
      agentsAdapter.uploadAgentSkill(input),
    onSuccess: async (_asset, input) => syncAgent(input.agentId),
  });

  const deleteSkill = useMutation({
    mutationFn: (input: { agentId: string; skillId: string }) =>
      agentsAdapter.deleteAgentSkill(input.agentId, input.skillId),
    onSuccess: async (_asset, input) => syncAgent(input.agentId),
  });

  return {
    uploadKnowledge,
    deleteKnowledge,
    uploadSkill,
    deleteSkill,
    isPending:
      uploadKnowledge.isPending ||
      deleteKnowledge.isPending ||
      uploadSkill.isPending ||
      deleteSkill.isPending,
  };
}
