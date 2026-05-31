import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDeleteAgent } from './useDeleteAgent';
import { mockAgents } from '@/lib/mockData';
import { useAgentStore } from '@/stores/agentStore';

vi.mock('@/lib/adapters/agents', () => ({
  deleteAgent: vi.fn().mockResolvedValue(undefined),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe('useDeleteAgent', () => {
  beforeEach(() => {
    useAgentStore.setState({
      agents: structuredClone(mockAgents),
      selectedAgentId: 'claude-code',
    });
  });

  it('removes local agent state after the backend confirms deletion', async () => {
    const { result } = renderHook(() => useDeleteAgent(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync('claude-code');
    });

    const state = useAgentStore.getState();
    expect(state.agents.some((agent) => agent.id === 'claude-code')).toBe(false);
    expect(state.selectedAgentId).not.toBe('claude-code');
  });
});
