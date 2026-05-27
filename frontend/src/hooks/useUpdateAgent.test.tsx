import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useUpdateAgent } from './useUpdateAgent';
import { mockAgents } from '@/lib/mockData';
import { useAgentStore } from '@/stores/agentStore';

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

  it('updates local agent state in mock mode', async () => {
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

  it('rejects when updating an unknown mock agent', async () => {
    const { result } = renderHook(() => useUpdateAgent(), { wrapper });
    let error: unknown;

    await act(async () => {
      try {
        await result.current.mutateAsync({
          agentId: 'missing-agent',
          input: { name: 'Missing' },
        });
      } catch (caught) {
        error = caught;
      }
    });

    expect(error).toEqual(new Error('Agent not found'));
  });
});
