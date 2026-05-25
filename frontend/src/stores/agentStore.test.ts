import { useAgentStore } from './agentStore';
import { mockAgents } from '@/lib/mockData';

function resetAgentStore() {
  useAgentStore.setState({
    agents: [...mockAgents],
    selectedAgentId: mockAgents[0]?.id ?? null,
  });
}

describe('agentStore', () => {
  beforeEach(() => {
    resetAgentStore();
  });

  it('creates a custom agent and selects it', () => {
    const created = useAgentStore.getState().createAgent({
      name: 'Frontend Reviewer',
      provider: 'custom',
      model: 'agenthub-demo-v1',
      capabilities: ['UI 审查', '测试补齐'],
      systemPrompt: '你负责审查前端 Demo。',
    });

    const state = useAgentStore.getState();
    expect(created).toMatchObject({
      id: 'frontend-reviewer',
      name: 'Frontend Reviewer',
      provider: 'custom',
      is_builtin: false,
      capabilities: ['UI 审查', '测试补齐'],
      system_prompt: '你负责审查前端 Demo。',
    });
    expect(state.agents[0]).toBe(created);
    expect(state.selectedAgentId).toBe(created.id);
  });

  it('generates unique ids for duplicate agent names', () => {
    const first = useAgentStore.getState().createAgent({
      name: 'Demo Agent',
      provider: 'custom',
      model: 'demo',
      capabilities: ['协作'],
      systemPrompt: '',
    });
    const second = useAgentStore.getState().createAgent({
      name: 'Demo Agent',
      provider: 'custom',
      model: 'demo',
      capabilities: ['协作'],
      systemPrompt: '',
    });

    expect(first.id).toBe('demo-agent');
    expect(second.id).toBe('demo-agent-1');
    expect(first.id).not.toBe(second.id);
    expect(second.system_prompt).toBeNull();
  });

  it('updates selected agent id', () => {
    useAgentStore.getState().setSelectedAgentId('codex-helper');
    expect(useAgentStore.getState().selectedAgentId).toBe('codex-helper');

    useAgentStore.getState().setSelectedAgentId(null);
    expect(useAgentStore.getState().selectedAgentId).toBeNull();
  });
});
