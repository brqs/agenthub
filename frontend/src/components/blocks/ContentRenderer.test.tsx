import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ContentRenderer } from './ContentRenderer';
import { mockAgents, type DemoContentBlock } from '@/lib/mockData';

vi.mock('./CodeBlock', () => ({
  CodeBlock: ({ language, code }: { language: string; code: string }) => (
    <div>
      code:{language}:{code}
    </div>
  ),
}));

describe('ContentRenderer', () => {
  function renderBlocks(blocks: DemoContentBlock[]) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <ContentRenderer blocks={blocks} agents={mockAgents} />
      </QueryClientProvider>,
    );
  }

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
        type: 'tool_call',
        call_id: 'call-1',
        tool_name: 'write_file',
        arguments: { path: 'public/demo.html' },
        status: 'ok',
        output_preview: 'wrote 120 bytes',
      },
      {
        type: 'deployment_status',
        deployment_id: 'deployment-1',
        kind: 'static_site',
        status: 'published',
        title: 'Static site deployment',
        url: 'https://example.com/deployed',
      },
      {
        type: 'agent_switch',
        from_agent: 'orchestrator',
        to_agent: 'codex-helper',
        task: '实现代码',
      },
    ];

    renderBlocks(blocks);

    expect(screen.getByText('AgentHub')).toBeInTheDocument();
    expect(screen.getByText('code:tsx:export function Demo() {}')).toBeInTheDocument();
    expect(screen.getByText('src/App.tsx')).toBeInTheDocument();
    expect(screen.getByText('Demo Preview')).toBeInTheDocument();
    expect(screen.getByText('demo.md')).toBeInTheDocument();
    expect(screen.getByText('任务卡')).toBeInTheDocument();
    expect(screen.getByText('write_file')).toBeInTheDocument();
    expect(screen.getByText('call-1')).toBeInTheDocument();
    expect(screen.getByText('Static site deployment')).toBeInTheDocument();
    expect(screen.getByText('已发布')).toBeInTheDocument();
    expect(screen.getByText('Orchestrator')).toBeInTheDocument();
    expect(screen.getByText('Codex Helper')).toBeInTheDocument();
  });

  it('renders fallback UI for unknown block types', () => {
    renderBlocks([{ type: 'chart', title: 'Demo Chart' } as unknown as DemoContentBlock]);

    expect(screen.getByText('未支持的消息块')).toBeInTheDocument();
    expect(screen.getByText(/chart/)).toBeInTheDocument();
  });
});
