import { create } from 'zustand';
import { mockAgents } from '@/lib/mockData';
import type { Agent, CreatableAgentProvider } from '@/lib/types';

export interface CreateAgentInput {
  name: string;
  provider: CreatableAgentProvider;
  model: string;
  command?: string;
  args?: string[];
  sdkOptions?: Record<string, unknown>;
  maxIterations?: number;
  timeoutSeconds?: number;
  capabilities: string[];
  systemPrompt: string;
}

interface AgentState {
  agents: Agent[];
  selectedAgentId: string | null;
  createAgent: (input: CreateAgentInput) => Agent;
  /** Insert an Agent returned from the backend (POST /agents). Prepends + selects. */
  addAgent: (agent: Agent) => void;
  /** Replace the agent list (used to mirror server state in API mode). */
  hydrateAgents: (agents: Agent[]) => void;
  updateAgentLocal: (agent: Agent) => void;
  removeAgentLocal: (agentId: string) => void;
  setSelectedAgentId: (agentId: string | null) => void;
  resetAgents: () => void;
  clearAgents: () => void;
}

function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

export const useAgentStore = create<AgentState>((set, get) => ({
  agents: mockAgents,
  selectedAgentId: mockAgents[0]?.id ?? null,
  createAgent: (input) => {
    const baseId = slugify(input.name) || 'user-agent';
    const existingIds = new Set(get().agents.map((agent) => agent.id));
    let id = baseId;
    let suffix = 1;
    while (existingIds.has(id)) {
      id = `${baseId}-${suffix}`;
      suffix += 1;
    }

    const agent: Agent = {
      id,
      name: input.name.trim(),
      provider: input.provider,
      avatar_url: '',
      capabilities: input.capabilities,
      system_prompt: input.systemPrompt.trim() || null,
      config: {
        model: input.model.trim() || 'deepseek',
        timeout_seconds: input.timeoutSeconds ?? 120,
        ...(input.provider === 'builtin'
          ? {
              model_backend: input.model.trim() || 'deepseek',
              max_iterations: input.maxIterations ?? 10,
              mcp_servers: [],
            }
          : {}),
        ...(input.provider === 'opencode'
          ? {
              command: input.command?.trim() || input.model.trim() || 'opencode',
              args: input.args ?? [],
            }
          : {}),
        ...(input.provider === 'claude_code'
          ? {
              sdk_options: input.sdkOptions ?? {},
            }
          : {}),
      },
      is_builtin: false,
      created_at: new Date().toISOString(),
    };

    set((state) => ({
      agents: [agent, ...state.agents],
      selectedAgentId: agent.id,
    }));

    return agent;
  },
  addAgent: (agent) =>
    set((state) => ({
      agents: [agent, ...state.agents.filter((existing) => existing.id !== agent.id)],
      selectedAgentId: agent.id,
    })),
  hydrateAgents: (agents) =>
    set((state) => {
      const remoteIds = new Set(agents.map((a) => a.id));
      const selected = state.selectedAgentId;
      const nextSelected =
        selected && remoteIds.has(selected) ? selected : agents[0]?.id ?? null;
      return { agents, selectedAgentId: nextSelected };
    }),
  updateAgentLocal: (agent) =>
    set((state) => ({
      agents: state.agents.map((item) => (item.id === agent.id ? agent : item)),
      selectedAgentId: agent.id,
    })),
  removeAgentLocal: (agentId) =>
    set((state) => {
      const nextAgents = state.agents.filter((agent) => agent.id !== agentId);
      return {
        agents: nextAgents,
        selectedAgentId:
          state.selectedAgentId === agentId
            ? nextAgents[0]?.id ?? null
            : state.selectedAgentId,
      };
    }),
  setSelectedAgentId: (agentId) => set({ selectedAgentId: agentId }),
  resetAgents: () => set({ agents: mockAgents, selectedAgentId: mockAgents[0]?.id ?? null }),
  clearAgents: () => set({ agents: [], selectedAgentId: null }),
}));
