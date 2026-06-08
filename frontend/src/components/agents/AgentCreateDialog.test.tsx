import { fireEvent, render, screen } from '@testing-library/react';
import { AgentCreateDialog } from './AgentCreateDialog';

vi.mock('@/hooks/useAgentTemplates', () => ({
  useAgentTemplates: () => ({
    data: {
      items: [
        {
          id: 'paper-research-assistant',
          name: 'Paper Helper',
          description: 'Organize research notes.',
          category: 'research',
          capabilities: ['research', 'writing'],
          builder_profile: {
            role: 'Research assistant',
            purpose: 'Organize papers',
            goals: ['Summarize notes'],
            tone: 'careful',
            do_not_do: ['Invent citations'],
            clarification_policy: 'ask_first',
            output_style: 'Use sections',
            starters: ['Summarize this note'],
          },
          permissions: {
            workspace_read: true,
            workspace_write: false,
            run_commands: 'never',
            network: 'never',
            deploy: 'never',
            external_accounts: 'never',
          },
          memory_policy: 'conversation',
          model_backend: 'deepseek',
        },
      ],
    },
  }),
}));

vi.mock('@/hooks/useModelAccounts', () => ({
  useModelProviders: () => ({
    data: {
      items: [
        {
          provider: 'deepseek',
          company_name: 'DeepSeek',
          protocol: 'openai_compatible',
          default_model: 'deepseek-v4-flash',
          models: ['deepseek-v4-flash'],
          requires_base_url: false,
          default_base_url: 'https://api.deepseek.com',
        },
      ],
    },
  }),
  useModelAccounts: () => ({
    accounts: { data: { items: [] } },
    create: { mutateAsync: vi.fn(), isPending: false },
    update: { mutateAsync: vi.fn(), isPending: false },
    remove: { mutateAsync: vi.fn(), isPending: false },
    verify: { mutateAsync: vi.fn(), isPending: false },
  }),
}));

function goToReview() {
  fireEvent.click(screen.getByRole('button', { name: '下一步' }));
  fireEvent.click(screen.getByRole('button', { name: '下一步' }));
  fireEvent.click(screen.getByRole('button', { name: '下一步' }));
}

describe('AgentCreateDialog', () => {
  it('submits no-code builder profile and safe builtin defaults', () => {
    const onCreate = vi.fn();
    render(<AgentCreateDialog open onClose={vi.fn()} onCreate={onCreate} />);

    expect(screen.getByText('快捷模板（可选）')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '不使用模板' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /论文资料整理助手/ })).not.toHaveClass('border-brand');

    fireEvent.change(screen.getByLabelText('名称'), {
      target: { value: 'My Research Agent' },
    });
    fireEvent.change(screen.getByLabelText('一句话用途'), {
      target: { value: 'Help me organize literature notes.' },
    });
    fireEvent.change(screen.getByLabelText('能力标签'), {
      target: { value: 'research, writing' },
    });
    goToReview();
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'My Research Agent',
        provider: 'builtin',
        model: 'deepseek',
        memoryPolicy: 'conversation',
        builderProfile: expect.objectContaining({
          clarification_policy: 'balanced',
          purpose: 'Help me organize literature notes.',
        }),
        permissions: expect.objectContaining({
          workspace_read: false,
          workspace_write: false,
        }),
      }),
    );
  });

  it('maps workspace and command permissions into the create payload', () => {
    const onCreate = vi.fn();
    render(<AgentCreateDialog open onClose={vi.fn()} onCreate={onCreate} />);

    fireEvent.change(screen.getByLabelText('名称'), {
      target: { value: 'Workspace Agent' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByLabelText('修改 Workspace 文件'));
    fireEvent.click(screen.getByLabelText('运行命令'));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        permissions: expect.objectContaining({
          workspace_read: true,
          workspace_write: true,
          run_commands: 'ask',
        }),
      }),
    );
  });

  it('blocks submit when advanced MCP JSON is invalid', () => {
    const onCreate = vi.fn();
    render(<AgentCreateDialog open onClose={vi.fn()} onCreate={onCreate} />);

    fireEvent.change(screen.getByLabelText('名称'), {
      target: { value: 'MCP Agent' },
    });
    goToReview();
    fireEvent.click(screen.getByRole('button', { name: '高级配置' }));
    fireEvent.change(screen.getByLabelText('MCP 服务器 JSON'), {
      target: { value: '{' },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    expect(screen.getByText('MCP 服务器配置必须是 JSON 数组。')).toBeInTheDocument();
    expect(onCreate).not.toHaveBeenCalled();
  });
});
