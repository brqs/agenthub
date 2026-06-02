import { fireEvent, render, screen } from '@testing-library/react';
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
    render(<AgentDetailPanel agent={agent} presentation="mobile" onClose={onClose} />);

    expect(screen.getByText('Agent 详情')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '关闭 Agent 详情' }));

    expect(onClose).toHaveBeenCalledOnce();
  });
});
