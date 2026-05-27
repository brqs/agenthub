import { fireEvent, render, screen } from '@testing-library/react';
import { AgentCreateDialog } from './AgentCreateDialog';

describe('AgentCreateDialog', () => {
  it('submits builtin agent runtime config fields', () => {
    const onCreate = vi.fn();
    render(<AgentCreateDialog open onClose={vi.fn()} onCreate={onCreate} />);

    fireEvent.change(screen.getByDisplayValue('Frontend Reviewer'), {
      target: { value: 'Planner Agent' },
    });
    fireEvent.change(screen.getByDisplayValue('deepseek'), {
      target: { value: 'deepseek-v4-flash' },
    });
    fireEvent.change(screen.getByDisplayValue('10'), {
      target: { value: '12' },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Planner Agent',
        provider: 'builtin',
        model: 'deepseek-v4-flash',
        maxIterations: 12,
      }),
    );
  });

  it('submits opencode command and args fields', () => {
    const onCreate = vi.fn();
    render(<AgentCreateDialog open onClose={vi.fn()} onCreate={onCreate} />);

    fireEvent.change(screen.getByLabelText('Provider'), {
      target: { value: 'opencode' },
    });
    fireEvent.change(screen.getByDisplayValue('opencode'), {
      target: { value: 'opencode-cli' },
    });
    fireEvent.change(screen.getByPlaceholderText('用空格分隔，例如 run --json'), {
      target: { value: 'run --json' },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: 'opencode',
        command: 'opencode-cli',
        args: ['run', '--json'],
        timeoutSeconds: 120,
      }),
    );
  });

  it('submits claude code sdk options as a json object', () => {
    const onCreate = vi.fn();
    render(<AgentCreateDialog open onClose={vi.fn()} onCreate={onCreate} />);

    fireEvent.change(screen.getByLabelText('Provider'), {
      target: { value: 'claude_code' },
    });
    fireEvent.change(screen.getByDisplayValue('claude-sonnet-4-6'), {
      target: { value: 'claude-sonnet-4-6-latest' },
    });
    fireEvent.change(screen.getByLabelText('SDK Options JSON'), {
      target: { value: '{ "permissionMode": "acceptEdits", "maxTurns": 6 }' },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: 'claude_code',
        model: 'claude-sonnet-4-6-latest',
        sdkOptions: {
          permissionMode: 'acceptEdits',
          maxTurns: 6,
        },
      }),
    );
  });

  it('blocks claude code submit when sdk options json is invalid', () => {
    const onCreate = vi.fn();
    render(<AgentCreateDialog open onClose={vi.fn()} onCreate={onCreate} />);

    fireEvent.change(screen.getByLabelText('Provider'), {
      target: { value: 'claude_code' },
    });
    fireEvent.change(screen.getByLabelText('SDK Options JSON'), {
      target: { value: '[' },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    expect(screen.getByText('请输入 JSON 对象')).toBeInTheDocument();
    expect(onCreate).not.toHaveBeenCalled();
  });
});
