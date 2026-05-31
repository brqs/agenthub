import { useAgentStore } from './agentStore';
import { mockAgents } from '@/lib/mockData';

describe('agentStore', () => {
  beforeEach(() => {
    useAgentStore.getState().clearAgents();
  });

  it('starts empty until backend agents are hydrated', () => {
    expect(useAgentStore.getState()).toMatchObject({
      agents: [],
      selectedAgentId: null,
    });
  });

  it('hydrates backend agents and selects the first available agent', () => {
    useAgentStore.getState().hydrateAgents(structuredClone(mockAgents));

    expect(useAgentStore.getState().agents).toEqual(mockAgents);
    expect(useAgentStore.getState().selectedAgentId).toBe(mockAgents[0]?.id);
  });

  it('adds, updates, and removes backend agents locally after mutations', () => {
    const agent = structuredClone(mockAgents[0]!);
    useAgentStore.getState().addAgent(agent);
    useAgentStore.getState().updateAgentLocal({ ...agent, name: 'Updated Agent' });

    expect(useAgentStore.getState().agents[0]).toMatchObject({
      id: agent.id,
      name: 'Updated Agent',
    });

    useAgentStore.getState().removeAgentLocal(agent.id);

    expect(useAgentStore.getState()).toMatchObject({
      agents: [],
      selectedAgentId: null,
    });
  });

  it('preserves the selected backend agent when hydrating a refreshed list', () => {
    useAgentStore.getState().hydrateAgents(structuredClone(mockAgents));
    useAgentStore.getState().setSelectedAgentId('codex-helper');
    useAgentStore.getState().hydrateAgents(structuredClone(mockAgents));

    expect(useAgentStore.getState().selectedAgentId).toBe('codex-helper');
  });
});
