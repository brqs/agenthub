import { render, screen } from '@testing-library/react';
import { ContentRenderer } from './ContentRenderer';
import type { DemoContentBlock } from '@/lib/mockData';

vi.mock('./CodeBlock', () => ({
  CodeBlock: ({ language, code }: { language: string; code: string }) => (
    <div>
      code:{language}:{code}
    </div>
  ),
}));

describe('ContentRenderer', () => {
  it('renders supported content block types', () => {
    const blocks: DemoContentBlock[] = [
      { type: 'text', text: 'Hello **AgentHub**' },
      { type: 'code', language: 'tsx', code: 'export function Demo() {}' },
      { type: 'diff', filename: 'src/App.tsx', before: 'old', after: 'new' },
      {
        type: 'web_preview',
        url: 'https://example.com/demo',
        title: 'Demo Preview',
        description: 'Preview description',
      },
      {
        type: 'file',
        filename: 'demo.md',
        url: 'https://example.com/demo.md',
        size: 1024,
        mime_type: 'text/markdown',
        preview_text: '# Demo',
      },
      {
        type: 'task_card',
        title: '任务卡',
        tasks: [{ id: 'task-1', agent_id: 'orchestrator', title: '拆解任务', status: 'done' }],
      },
      {
        type: 'agent_switch',
        from_agent: 'orchestrator',
        to_agent: 'codex-helper',
        task: '实现代码',
      },
    ];

    render(<ContentRenderer blocks={blocks} />);

    expect(screen.getByText('AgentHub')).toBeInTheDocument();
    expect(screen.getByText('code:tsx:export function Demo() {}')).toBeInTheDocument();
    expect(screen.getByText('src/App.tsx')).toBeInTheDocument();
    expect(screen.getByText('Demo Preview')).toBeInTheDocument();
    expect(screen.getByText('demo.md')).toBeInTheDocument();
    expect(screen.getByText('任务卡')).toBeInTheDocument();
    expect(screen.getByText('Orchestrator → Codex Helper')).toBeInTheDocument();
  });

  it('renders fallback UI for unknown block types', () => {
    render(
      <ContentRenderer
        blocks={[{ type: 'chart', title: 'Demo Chart' } as unknown as DemoContentBlock]}
      />,
    );

    expect(screen.getByText('未支持的消息块')).toBeInTheDocument();
    expect(screen.getByText(/chart/)).toBeInTheDocument();
  });
});
