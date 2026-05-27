import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AgentEditDialog } from './AgentEditDialog';
import type { Agent } from '@/lib/types';

const agent: Agent = {
  id: 'frontend-reviewer',
  name: 'Frontend Reviewer',
  provider: 'builtin',
  avatar_url: '',
  capabilities: ['UI 审查', '测试补齐'],
  system_prompt: '检查前端体验。',
  config: { model_backend: 'deepseek', max_iterations: 10 },
  is_builtin: false,
  created_at: new Date().toISOString(),
};

describe('AgentEditDialog', () => {
  it('submits editable agent fields', async () => {
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    render(
      <AgentEditDialog
        open
        agent={agent}
        onClose={vi.fn()}
        onUpdate={onUpdate}
      />,
    );

    fireEvent.change(screen.getByDisplayValue('Frontend Reviewer'), {
      target: { value: 'UX Reviewer' },
    });
    fireEvent.change(screen.getByDisplayValue('UI 审查, 测试补齐'), {
      target: { value: '体验复核, 可访问性' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() =>
      expect(onUpdate).toHaveBeenCalledWith('frontend-reviewer', {
        name: 'UX Reviewer',
        avatar_url: '',
        capabilities: ['体验复核', '可访问性'],
        system_prompt: '检查前端体验。',
      }),
    );
  });
});
