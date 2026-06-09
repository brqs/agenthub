import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AgentDetailPanel } from './AgentDetailPanel';
import type { Agent } from '@/lib/types';

const agent: Agent = {
  id: 'frontend-reviewer',
  name: 'Frontend Reviewer',
  provider: 'builtin',
  avatar_url: '',
  capabilities: ['UI 审查'],
  system_prompt: '检查前端体验。',
  config: { model: 'deepseek' },
  is_builtin: false,
  created_at: new Date().toISOString(),
};

describe('AgentDetailPanel', () => {
  it('renders and closes its mobile presentation', () => {
    const onClose = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <AgentDetailPanel agent={agent} presentation="mobile" onClose={onClose} />
      </QueryClientProvider>,
    );

    expect(screen.getByText('Agent 详情')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '关闭 Agent 详情' }));

    expect(onClose).toHaveBeenCalledOnce();
  });
});
