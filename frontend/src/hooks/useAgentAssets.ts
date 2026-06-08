import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { queryKeys } from '@/lib/queryKeys';
import type { AgentKnowledgeUsage } from '@/lib/types';
import { useAgentStore } from '@/stores/agentStore';
import { useAuthStore } from '@/stores/authStore';

async function refreshAgent(agentId: string) {
  const agents = await agentsAdapter.listAgents();
  return agents.find((agent) => agent.id === agentId) ?? null;
}

export function useAgentAssets(agentId?: string | null) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);
  const updateAgentLocal = useAgentStore((state) => state.updateAgentLocal);

  async function syncAgent(agentId: string) {
    const agent = await refreshAgent(agentId);
    if (agent) updateAgentLocal(agent);
    void queryClient.invalidateQueries({ queryKey: queryKeys.agents(userId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.agentAssets(userId, agentId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.agentAssetHistory(userId, agentId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.agentAssetUsage(userId, agentId) });
  }

  const assets = useQuery({
    queryKey: queryKeys.agentAssets(userId, agentId),
    queryFn: () => agentsAdapter.listAgentAssets(agentId ?? ''),
    enabled: Boolean(userId && agentId),
  });

  const history = useQuery({
    queryKey: queryKeys.agentAssetHistory(userId, agentId),
    queryFn: () => agentsAdapter.listAgentAssetHistory(agentId ?? '', 20),
    enabled: Boolean(userId && agentId),
  });

  const usage = useQuery({
    queryKey: queryKeys.agentAssetUsage(userId, agentId),
    queryFn: () => agentsAdapter.listAgentAssetUsage(agentId ?? '', 20),
    enabled: Boolean(userId && agentId),
  });

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

  const updateKnowledge = useMutation({
    mutationFn: (input: {
      agentId: string;
      uploadId: string;
      label?: string;
      usage?: AgentKnowledgeUsage;
    }) =>
      agentsAdapter.updateAgentKnowledge(input.agentId, input.uploadId, {
        label: input.label,
        usage: input.usage,
      }),
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

  const updateSkill = useMutation({
    mutationFn: (input: {
      agentId: string;
      skillId: string;
      name?: string;
      description?: string;
    }) =>
      agentsAdapter.updateAgentSkill(input.agentId, input.skillId, {
        name: input.name,
        description: input.description,
      }),
    onSuccess: async (_asset, input) => syncAgent(input.agentId),
  });

  return {
    assets,
    history,
    usage,
    uploadKnowledge,
    deleteKnowledge,
    updateKnowledge,
    uploadSkill,
    deleteSkill,
    updateSkill,
    isPending:
      uploadKnowledge.isPending ||
      deleteKnowledge.isPending ||
      updateKnowledge.isPending ||
      uploadSkill.isPending ||
      deleteSkill.isPending ||
      updateSkill.isPending,
  };
}
