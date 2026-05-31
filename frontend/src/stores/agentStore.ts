import { create } from 'zustand';
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
  /** Insert an Agent returned from the backend (POST /agents). Prepends + selects. */
  addAgent: (agent: Agent) => void;
  /** Replace the agent list (used to mirror server state in API mode). */
  hydrateAgents: (agents: Agent[]) => void;
  updateAgentLocal: (agent: Agent) => void;
  removeAgentLocal: (agentId: string) => void;
  setSelectedAgentId: (agentId: string | null) => void;
  clearAgents: () => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: [],
  selectedAgentId: null,
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
  clearAgents: () => set({ agents: [], selectedAgentId: null }),
}));
