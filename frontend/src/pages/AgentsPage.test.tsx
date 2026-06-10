import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AgentsPage } from './AgentsPage';
import { mockAgents } from '@/lib/mockData';
import { useAgentStore } from '@/stores/agentStore';

vi.mock('@/lib/adapters/agents', () => ({
  listAgents: vi.fn().mockResolvedValue([]),
  listAgentAssets: vi.fn().mockResolvedValue({ knowledge: [], skills: [], bindings: [] }),
  listAgentAssetHistory: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  listAgentAssetUsage: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createAgent: vi.fn().mockImplementation(async (input) => ({
    id: 'planner-agent',
    ...input,
    is_builtin: false,
    created_at: '2026-05-31T00:00:00.000Z',
  })),
  getAgent: vi.fn().mockImplementation(async (agentId) => ({
    id: agentId,
    name: 'Planner Agent',
    provider: 'opencode',
    avatar_url: '',
    capabilities: ['前端实现'],
    system_prompt: '角色：前端实现助手',
    config: {
      custom_agent_mode: 'server_agent_wrapper',
      base_agent_id: 'opencode-helper',
      wrapper_profile: {
        purpose: '负责前端实现。',
        planning_profile: '前端实现任务优先调用。',
      },
    },
    is_builtin: false,
    created_at: '2026-05-31T00:00:00.000Z',
  })),
  updateAgent: vi.fn(),
  deleteAgent: vi.fn(),
  uploadAgentSkill: vi.fn(),
  deleteAgentSkill: vi.fn(),
  updateAgentSkill: vi.fn(),
  testRunAgent: vi.fn(),
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

  it('creates a server wrapper agent and opens its detail state', async () => {
    renderAgentsPage();

    fireEvent.click(screen.getByRole('button', { name: '创建 Agent' }));
    const dialog = screen.getByRole('heading', { name: '创建服务器 Agent 套壳' }).closest('form');
    expect(dialog).not.toBeNull();
    fireEvent.click(within(dialog as HTMLElement).getByRole('button', { name: /OpenCode Helper/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.change(screen.getByLabelText('名称'), {
      target: { value: 'Planner Agent' },
    });
    fireEvent.change(screen.getByLabelText('一句话用途'), {
      target: { value: '负责前端实现。' },
    });
    fireEvent.change(screen.getByLabelText('调度描述'), {
      target: { value: '前端实现任务优先调用。' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    await waitFor(() => expect(screen.getAllByText('Planner Agent').length).toBeGreaterThan(0));
    expect(screen.getAllByText('我的 Agent').length).toBeGreaterThan(0);
    expect(screen.getByText('编辑')).toBeInTheDocument();
    expect(screen.getByText('删除')).toBeInTheDocument();
  });
});
