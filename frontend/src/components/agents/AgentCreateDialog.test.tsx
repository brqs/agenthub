import { fireEvent, render, screen } from '@testing-library/react';
import { AgentCreateDialog } from './AgentCreateDialog';

function fillRequiredProfile() {
  fireEvent.click(screen.getByRole('button', { name: /OpenCode Helper/ }));
  fireEvent.click(screen.getByRole('button', { name: '下一步' }));
  fireEvent.change(screen.getByLabelText('名称'), {
    target: { value: '前端页面实现助手' },
  });
  fireEvent.change(screen.getByLabelText('一句话用途'), {
    target: { value: '负责实现静态网页和交互效果。' },
  });
  fireEvent.change(screen.getByLabelText('角色'), {
    target: { value: '资深前端实现者' },
  });
  fireEvent.change(screen.getByLabelText('调度描述'), {
    target: { value: '当任务需要生成 HTML、CSS、JS 或修复前端页面时调用。' },
  });
  fireEvent.change(screen.getByLabelText('能力标签'), {
    target: { value: '前端实现, 静态网页' },
  });
}

describe('AgentCreateDialog', () => {
  it('creates a server agent wrapper payload', () => {
    const onCreate = vi.fn();
    render(<AgentCreateDialog open onClose={vi.fn()} onCreate={onCreate} />);

    expect(screen.getByText('创建服务器 Agent 套壳')).toBeInTheDocument();
    expect(screen.queryByText('高级配置')).not.toBeInTheDocument();
    expect(screen.queryByText('AgentHub 免费 DeepSeek')).not.toBeInTheDocument();

    fillRequiredProfile();
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: '前端页面实现助手',
        provider: 'opencode',
        baseAgentId: 'opencode-helper',
        capabilities: ['前端实现', '静态网页'],
        systemPrompt: expect.stringContaining('角色：资深前端实现者'),
        wrapperProfile: expect.objectContaining({
          purpose: '负责实现静态网页和交互效果。',
          planning_profile: '当任务需要生成 HTML、CSS、JS 或修复前端页面时调用。',
          capabilities: ['前端实现', '静态网页'],
        }),
      }),
    );
  });

  it('requires a selected base agent before submit', () => {
    const onCreate = vi.fn();
    render(<AgentCreateDialog open onClose={vi.fn()} onCreate={onCreate} />);

    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.change(screen.getByLabelText('名称'), {
      target: { value: '未选择底座' },
    });
    fireEvent.change(screen.getByLabelText('一句话用途'), {
      target: { value: '测试用途' },
    });
    fireEvent.change(screen.getByLabelText('调度描述'), {
      target: { value: '测试调度描述' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    expect(screen.getByText('请先选择一个服务器底座 Agent。')).toBeInTheDocument();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it('collects markdown skill files', () => {
    const onCreate = vi.fn();
    render(<AgentCreateDialog open onClose={vi.fn()} onCreate={onCreate} />);
    fillRequiredProfile();
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const skill = new File(['# Skill'], 'SKILL.md', { type: 'text/markdown' });
    const ignored = new File(['zip'], 'skill.zip', { type: 'application/zip' });
    fireEvent.change(input, { target: { files: [skill, ignored] } });

    expect(screen.getByText('SKILL.md')).toBeInTheDocument();
    expect(screen.queryByText('skill.zip')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        skillFiles: [skill],
      }),
    );
  });
});
