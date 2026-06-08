import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { queryKeys } from '@/lib/queryKeys';
import type { Agent, CreateAgentRequest } from '@/lib/types';
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

function inferModelBackendFromProfile(
  input: CreateAgentInput,
  fallbackModel: string,
): 'claude' | 'openai' | 'deepseek' {
  const profile = input.modelProfile;
  if (profile?.source === 'user_account') {
    if (profile.provider === 'anthropic') return 'claude';
    if (profile.provider === 'deepseek') return 'deepseek';
    return 'openai';
  }
  return inferModelBackend(fallbackModel);
}

function allowedToolsFromPermissions(input: CreateAgentInput): string[] | undefined {
  if (input.allowedTools) return input.allowedTools;
  const permissions = input.permissions;
  if (!permissions) return undefined;
  const tools: string[] = [];
  if (permissions.workspace_read || permissions.workspace_write) tools.push('read_file');
  if (permissions.workspace_write) tools.push('write_file');
  if (permissions.run_commands !== 'never') tools.push('bash');
  return tools;
}

export function buildAgentConfig(input: CreateAgentInput): Record<string, unknown> {
  const value = input.model.trim() || DEFAULT_MODELS[input.provider];
  const timeoutSeconds = input.timeoutSeconds ?? 120;

  if (input.provider === 'builtin') {
    const config: Record<string, unknown> = {
      model_backend: inferModelBackendFromProfile(input, value),
      model_profile: input.modelProfile ?? {
        source: 'agenthub_default',
        provider: 'deepseek',
        model: 'deepseek-v4-flash',
      },
      max_iterations: input.maxIterations ?? 10,
      mcp_servers: input.mcpServers ?? [],
    };
    const allowedTools = allowedToolsFromPermissions(input);
    if (allowedTools) config.allowed_tools = allowedTools;
    if (input.builderProfile) config.builder_profile = input.builderProfile;
    if (input.permissions) config.permissions = input.permissions;
    if (input.memoryPolicy) config.memory_policy = input.memoryPolicy;
    return config;
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
  const addAgent = useAgentStore((state) => state.addAgent);

  const apiMutation = useMutation({
    mutationFn: (input: CreateAgentInput) =>
      agentsAdapter.createAgent({
        name: input.name.trim(),
        provider: input.provider,
        avatar_url: '',
        capabilities: input.capabilities,
        system_prompt: input.systemPrompt.trim() || null,
        config: buildAgentConfig(input) as CreateAgentRequest['config'],
      }),
    onSuccess: (created) => {
      addAgent(created);
      void queryClient.invalidateQueries({ queryKey: queryKeys.agents(userId) });
    },
  });

  return {
    mutateAsync: (input: CreateAgentInput): Promise<Agent> => apiMutation.mutateAsync(input),
    isPending: apiMutation.isPending,
  };
}
