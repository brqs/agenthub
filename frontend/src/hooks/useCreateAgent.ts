import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { env } from '@/lib/env';
import type { Agent } from '@/lib/types';
import { useAgentStore, type CreateAgentInput } from '@/stores/agentStore';

const DEFAULT_MODELS: Record<CreateAgentInput['provider'], string> = {
  claude: 'claude-sonnet-4-6',
  openai: 'gpt-4o',
  deepseek: 'deepseek-v4-flash',
  custom: 'claude-sonnet-4-6',
};

function inferUpstreamProvider(model: string): 'claude' | 'openai' | 'deepseek' {
  if (model.startsWith('gpt-')) return 'openai';
  if (model.startsWith('deepseek-')) return 'deepseek';
  return 'claude';
}

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
        config: {
          model: input.model.trim() || DEFAULT_MODELS[input.provider],
          temperature: 0.4,
          ...(input.provider === 'custom'
            ? {
                upstream_provider: inferUpstreamProvider(
                  input.model.trim() || DEFAULT_MODELS.custom,
                ),
              }
            : {}),
        },
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
