import { create } from 'zustand';
import { mockAgents } from '@/lib/mockData';
import type { Agent, CreatableAgentProvider } from '@/lib/types';

export interface CreateAgentInput {
  name: string;
  provider: CreatableAgentProvider;
  model: string;
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
  setSelectedAgentId: (agentId: string | null) => void;
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
        ...(input.provider === 'builtin'
          ? { model_backend: input.model.trim() || 'deepseek', max_iterations: 10 }
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
  setSelectedAgentId: (agentId) => set({ selectedAgentId: agentId }),
}));
