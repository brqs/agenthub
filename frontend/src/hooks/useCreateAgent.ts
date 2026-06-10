import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { queryKeys } from '@/lib/queryKeys';
import type { Agent, CreateAgentRequest } from '@/lib/types';
import { useAgentStore, type CreateAgentInput } from '@/stores/agentStore';
import { useAuthStore } from '@/stores/authStore';

export function buildAgentConfig(input: CreateAgentInput): Record<string, unknown> {
  return {
    custom_agent_mode: 'server_agent_wrapper',
    base_agent_id: input.baseAgentId,
    wrapper_profile: input.wrapperProfile,
  };
}

export function useCreateAgent() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);
  const addAgent = useAgentStore((state) => state.addAgent);

  const apiMutation = useMutation({
    mutationFn: async (input: CreateAgentInput) => {
      const created = await agentsAdapter.createAgent({
        name: input.name.trim(),
        provider: input.provider,
        avatar_url: '',
        capabilities: input.capabilities,
        system_prompt: input.systemPrompt.trim() || null,
        config: buildAgentConfig(input) as CreateAgentRequest['config'],
      });
      for (const file of input.skillFiles ?? []) {
        await agentsAdapter.uploadAgentSkill({
          agentId: created.id,
          file,
        });
      }
      if (input.skillFiles?.length) {
        return agentsAdapter.getAgent(created.id);
      }
      return created;
    },
    onSuccess: (created) => {
      addAgent(created);
      void queryClient.invalidateQueries({ queryKey: queryKeys.agents(userId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.agentAssets(userId, created.id) });
    },
  });

  return {
    mutateAsync: (input: CreateAgentInput): Promise<Agent> => apiMutation.mutateAsync(input),
    isPending: apiMutation.isPending,
  };
}
