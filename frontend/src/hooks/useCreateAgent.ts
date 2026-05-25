import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { env } from '@/lib/env';
import type { Agent } from '@/lib/types';
import { useAgentStore, type CreateAgentInput } from '@/stores/agentStore';

export function useCreateAgent() {
  const queryClient = useQueryClient();
  const createMockAgent = useAgentStore((state) => state.createAgent);
  const addAgent = useAgentStore((state) => state.addAgent);
  const [mockPending, setMockPending] = useState(false);

  const apiMutation = useMutation({
    mutationFn: (input: CreateAgentInput) =>
      agentsAdapter.createAgent({
        name: input.name.trim(),
        provider: input.provider,
        avatar_url: '',
        capabilities: input.capabilities,
        system_prompt: input.systemPrompt.trim() || null,
        config: { model: input.model.trim() || 'custom-demo-model', temperature: 0.4 },
      }),
    onSuccess: (created) => {
      addAgent(created);
      void queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });

  async function mutateAsync(input: CreateAgentInput): Promise<Agent> {
    if (env.useMockApi) {
      setMockPending(true);
      try {
        await new Promise((resolve) => window.setTimeout(resolve, 120));
        return createMockAgent(input);
      } finally {
        setMockPending(false);
      }
    }
    return apiMutation.mutateAsync(input);
  }

  return {
    mutateAsync,
    isPending: env.useMockApi ? mockPending : apiMutation.isPending,
  };
}
