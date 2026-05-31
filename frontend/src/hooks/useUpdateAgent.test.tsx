import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useUpdateAgent } from './useUpdateAgent';
import { mockAgents } from '@/lib/mockData';
import { useAgentStore } from '@/stores/agentStore';

vi.mock('@/lib/adapters/agents', () => ({
  updateAgent: vi.fn().mockImplementation(async (agentId, input) => ({
    ...mockAgents.find((agent) => agent.id === agentId),
    ...input,
    id: agentId,
  })),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe('useUpdateAgent', () => {
  beforeEach(() => {
    useAgentStore.setState({
      agents: structuredClone(mockAgents),
      selectedAgentId: mockAgents[0]?.id ?? null,
    });
  });

  it('updates local agent state after the backend confirms the update', async () => {
    const { result } = renderHook(() => useUpdateAgent(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        agentId: 'claude-code',
        input: {
          name: 'Claude Reviewer',
          capabilities: ['代码复核'],
          system_prompt: 'Review code.',
        },
      });
    });

    expect(useAgentStore.getState().agents.find((agent) => agent.id === 'claude-code')).toMatchObject({
      name: 'Claude Reviewer',
      capabilities: ['代码复核'],
      system_prompt: 'Review code.',
    });
  });

});
