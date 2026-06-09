import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AgentsPage } from './AgentsPage';
import { mockAgents } from '@/lib/mockData';
import { useAgentStore } from '@/stores/agentStore';

vi.mock('@/lib/adapters/agents', () => ({
  listAgents: vi.fn().mockResolvedValue([]),
  listAgentTemplates: vi.fn().mockResolvedValue({ items: [] }),
  listModelProviders: vi.fn().mockResolvedValue({ items: [] }),
  listModelAccounts: vi.fn().mockResolvedValue({ items: [] }),
  createModelAccount: vi.fn(),
  updateModelAccount: vi.fn(),
  deleteModelAccount: vi.fn(),
  verifyModelAccount: vi.fn(),
  createAgent: vi.fn().mockImplementation(async (input) => ({
    id: 'planner-agent',
    ...input,
    is_builtin: false,
    created_at: '2026-05-31T00:00:00.000Z',
  })),
  updateAgent: vi.fn(),
  deleteAgent: vi.fn(),
}));

function renderAgentsPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AgentsPage />
    </QueryClientProvider>,
  );
}

describe('AgentsPage', () => {
  beforeEach(() => {
    useAgentStore.setState({
      agents: structuredClone(mockAgents),
      selectedAgentId: mockAgents[0]?.id ?? null,
    });
  });

  it('shows registry groups and filters agents by search', () => {
    renderAgentsPage();

    expect(screen.getByText('Agent 管理')).toBeInTheDocument();
    expect(screen.getAllByText('我的 Agent').length).toBeGreaterThan(0);
    expect(screen.getAllByText('内置 Agent').length).toBeGreaterThan(0);

    fireEvent.change(screen.getByPlaceholderText('搜索 Agent、Provider 或能力'), {
      target: { value: 'OpenCode Helper' },
    });

    expect(screen.getAllByText('OpenCode Helper').length).toBeGreaterThan(0);
    expect(screen.queryByText('Claude Code')).not.toBeInTheDocument();
  });

  it('creates a custom agent and opens its detail state', async () => {
    renderAgentsPage();

    fireEvent.click(screen.getByRole('button', { name: '创建 Agent' }));
    fireEvent.change(screen.getByLabelText('名称'), {
      target: { value: 'Planner Agent' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    await waitFor(() => expect(screen.getAllByText('Planner Agent')).toHaveLength(2));
    expect(screen.getAllByText('我的 Agent').length).toBeGreaterThan(0);
    expect(screen.getByText('编辑')).toBeInTheDocument();
    expect(screen.getByText('删除')).toBeInTheDocument();
  });
});
