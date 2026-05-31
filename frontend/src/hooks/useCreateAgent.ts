import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { env } from '@/lib/env';
import { queryKeys } from '@/lib/queryKeys';
import type { Agent } from '@/lib/types';
import { useAgentStore, type CreateAgentInput } from '@/stores/agentStore';
import { useAuthStore } from '@/stores/authStore';

const DEFAULT_MODELS: Record<CreateAgentInput['provider'], string> = {
  builtin: 'deepseek',
  claude_code: 'claude-sonnet-4-6',
  codex: 'gpt-4o',
  opencode: 'opencode',
};

function inferModelBackend(model: string): 'claude' | 'openai' | 'deepseek' {
  if (model.startsWith('gpt-')) return 'openai';
  if (model === 'deepseek' || model.startsWith('deepseek-')) return 'deepseek';
  return 'claude';
}

export function buildAgentConfig(input: CreateAgentInput): Record<string, unknown> {
  const value = input.model.trim() || DEFAULT_MODELS[input.provider];
  const timeoutSeconds = input.timeoutSeconds ?? 120;

  if (input.provider === 'builtin') {
    return {
      model_backend: inferModelBackend(value),
      max_iterations: input.maxIterations ?? 10,
      mcp_servers: [],
    };
  }

  if (input.provider === 'opencode') {
    return {
      command: input.command?.trim() || value,
      args: input.args ?? [],
      timeout_seconds: timeoutSeconds,
    };
  }

  if (input.provider === 'claude_code') {
    return {
      sdk_options: {
        model: value,
        ...(input.sdkOptions ?? {}),
      },
      timeout_seconds: timeoutSeconds,
    };
  }

  return {
    model: value,
    timeout_seconds: timeoutSeconds,
  };
}

export function useCreateAgent() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);
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
        config: buildAgentConfig(input),
      }),
    onSuccess: (created) => {
      addAgent(created);
      void queryClient.invalidateQueries({ queryKey: queryKeys.agents(userId) });
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
