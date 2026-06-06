import { fireEvent, render, screen } from '@testing-library/react';
import { ProcessBlock } from './ProcessBlock';
import type { ProcessBlock as ProcessBlockType } from '@/lib/types';

const processBlock: ProcessBlockType = {
  type: 'process',
  agent_id: 'orchestrator',
  title: '执行过程',
  status: 'running',
  default_collapsed: true,
  summary: '正在整理公开执行过程。',
  metadata: { source: 'orchestrator_process' },
  steps: [
    {
      id: 'step-1',
      label: '分析用户请求并生成执行计划',
      kind: 'planning',
      status: 'done',
      detail: '已生成公开可展示的任务拆解。',
      agent_id: 'orchestrator',
    },
    {
      id: 'step-2',
      label: '调用子 Agent 完成实现',
      kind: 'dispatch',
      status: 'running',
      detail: '等待子 Agent 返回产物。',
      agent_id: 'claude_code',
    },
  ],
};

describe('ProcessBlock', () => {
  it('uses default_collapsed and can expand or collapse process details', () => {
    render(<ProcessBlock block={processBlock} />);

    expect(screen.getByText('执行过程')).toBeInTheDocument();
    expect(screen.getByText('进行中')).toBeInTheDocument();
    expect(screen.getByText('正在整理公开执行过程。')).toBeInTheDocument();
    expect(screen.getByText('2 个步骤')).toBeInTheDocument();
    expect(screen.queryByText('分析用户请求并生成执行计划')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '展开执行过程' }));

    expect(screen.getByText('分析用户请求并生成执行计划')).toBeInTheDocument();
    expect(screen.getByText('调用子 Agent 完成实现')).toBeInTheDocument();
    expect(screen.getByText('已生成公开可展示的任务拆解。')).toBeInTheDocument();
    expect(screen.getByText('计划')).toBeInTheDocument();
    expect(screen.getByText('执行')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '收起执行过程' }));

    expect(screen.queryByText('分析用户请求并生成执行计划')).not.toBeInTheDocument();
  });

  it('renders expanded details when default_collapsed is false', () => {
    render(<ProcessBlock block={{ ...processBlock, default_collapsed: false, status: 'done' }} />);

    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(screen.getByText('分析用户请求并生成执行计划')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '收起执行过程' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });
});
