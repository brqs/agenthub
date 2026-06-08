import { fireEvent, render, screen } from '@testing-library/react';
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

vi.mock('./SyntaxHighlightedCode', () => ({
  SyntaxHighlightedCode: ({ code }: { code: string }) => <pre>{code}</pre>,
}));

describe('ContentRenderer', () => {
  function renderBlocks(blocks: DemoContentBlock[], options: { streaming?: boolean } = {}) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <ContentRenderer blocks={blocks} agents={mockAgents} streaming={options.streaming ?? true} />
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
        path: 'docs/demo.md',
        artifact_kind: 'document',
        filename: 'demo.md',
        url: 'https://example.com/demo.md',
        size: 1024,
        mime_type: 'text/markdown',
        preview_text: '# Demo',
        preview_truncated: false,
        metadata: {},
      },
      {
        type: 'task_card',
        title: '任务卡',
        tasks: [{ id: 'task-1', agent_id: 'orchestrator', title: '拆解任务', status: 'done' }],
      },
      {
        type: 'process',
        agent_id: 'orchestrator',
        title: '执行过程',
        status: 'partial',
        default_collapsed: false,
        summary: '公开执行过程部分完成。',
        metadata: {},
        steps: [
          {
            label: '整理执行计划',
            kind: 'planning',
            status: 'done',
            detail: '共 2 个公开执行步骤。',
          },
          {
            label: '移动端验收',
            kind: 'evaluation',
            status: 'error',
            detail: '1 项需要注意。',
          },
        ],
      },
      {
        type: 'clarification',
        agent_id: 'orchestrator',
        mode: 'grill_me',
        title: '需求追问',
        status: 'waiting',
        current_question: {
          id: 'audience_goal',
          question: '目标用户是谁？',
          reason: '先锁定使用场景。',
          recommended_answer: '普通用户，桌面和移动端都可用。',
          options: ['使用推荐答案'],
          status: 'pending',
        },
        questions: [],
        metadata: {},
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
        type: 'attachment',
        upload_id: 'upload-1',
        filename: 'mockup.png',
        content_type: 'image/png',
        size_bytes: 2048,
        purpose: 'message_attachment',
        safety_status: 'passed',
        preview: { kind: 'image', thumbnail_url: 'https://example.com/mockup.png' },
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
        type: 'workflow',
        name: 'Demo Workflow',
        format: 'json',
        definition: {
          version: '1',
          name: 'Demo Workflow',
          nodes: [
            { id: 'start', type: 'trigger' },
            { id: 'publish', type: 'action' },
          ],
          edges: [{ source: 'start', target: 'publish' }],
        },
        nodes: [
          { id: 'start', type: 'trigger' },
          { id: 'publish', type: 'action' },
        ],
        edges: [{ source: 'start', target: 'publish' }],
        validation_status: 'passed',
        runtime_status: 'ready',
        dry_run_status: 'not_supported',
        health_status: 'passed',
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
    expect(screen.getByText('文档')).toBeInTheDocument();
    expect(screen.getByText('任务卡')).toBeInTheDocument();
    expect(screen.getByText('执行过程')).toBeInTheDocument();
    expect(screen.getByText('部分完成')).toBeInTheDocument();
    expect(screen.getByText('整理执行计划')).toBeInTheDocument();
    expect(screen.getByText('移动端验收')).toBeInTheDocument();
    expect(screen.getByText('需求追问')).toBeInTheDocument();
    expect(screen.getByText('目标用户是谁？')).toBeInTheDocument();
    expect(screen.getByText('普通用户，桌面和移动端都可用。')).toBeInTheDocument();
    expect(screen.getByText(/只会填入输入框/)).toBeInTheDocument();
    expect(screen.getByText('write_file')).toBeInTheDocument();
    expect(screen.getByText('call-1')).toBeInTheDocument();
    expect(screen.getByText('mockup.png')).toBeInTheDocument();
    expect(screen.getByText('图片')).toBeInTheDocument();
    expect(screen.getByText('Static site deployment')).toBeInTheDocument();
    expect(screen.getByText('已发布')).toBeInTheDocument();
    expect(screen.getByText('Demo Workflow')).toBeInTheDocument();
    expect(screen.getByText('start · trigger')).toBeInTheDocument();
    expect(screen.getByText('start -> publish')).toBeInTheDocument();
    expect(screen.getByText('Orchestrator')).toBeInTheDocument();
    expect(screen.getByText('Codex Helper')).toBeInTheDocument();
  });

  it('renders fallback UI for unknown block types', () => {
    renderBlocks([{ type: 'chart', title: 'Demo Chart' } as unknown as DemoContentBlock]);

    expect(screen.getByText('未支持的消息块')).toBeInTheDocument();
    expect(screen.getByText(/chart/)).toBeInTheDocument();
  });

  it('collapses execution presentation blocks after streaming completes', () => {
    const blocks: DemoContentBlock[] = [
      {
        type: 'process',
        agent_id: 'orchestrator',
        title: '执行过程',
        status: 'done',
        default_collapsed: false,
        metadata: {},
        steps: [
          { label: '整理计划', kind: 'planning', status: 'done' },
          { label: '调用工具', kind: 'tool', status: 'done' },
        ],
        presentation: {
          role: 'execution_process',
          collapsible: true,
          group_id: 'execution-main',
          boundary: 'execution_start',
          label: '执行过程',
        },
      },
      {
        type: 'text',
        text: 'Reading files',
        presentation: {
          role: 'execution_text',
          collapsible: true,
          group_id: 'execution-main',
          label: '执行过程',
        },
      },
      {
        type: 'tool_call',
        call_id: 'call-read',
        tool_name: 'Read',
        arguments: { path: 'index.html' },
        status: 'ok',
        presentation: {
          role: 'tool_trace',
          collapsible: true,
          group_id: 'execution-main',
        },
      },
      {
        type: 'text',
        text: '阶段总结：已完成文件检查。',
        presentation: {
          role: 'agent_summary',
          collapsible: false,
          boundary: 'answer_start',
          closes_group_id: 'execution-main',
        },
      },
      {
        type: 'text',
        text: '最终回答：任务已完成。',
        presentation: {
          role: 'final_answer',
          collapsible: false,
          boundary: 'answer_start',
          closes_group_id: 'execution-main',
        },
      },
    ];

    renderBlocks(blocks, { streaming: false });

    expect(screen.getByText('阶段总结：已完成文件检查。')).toBeInTheDocument();
    expect(screen.getByText('最终回答：任务已完成。')).toBeInTheDocument();
    expect(screen.queryByText('Reading files')).not.toBeInTheDocument();
    expect(screen.queryByText('call-read')).not.toBeInTheDocument();
    expect(screen.getByText('2 步骤 · 1 工具 · 3 项')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /执行过程/ }));

    expect(screen.getByText('整理计划')).toBeInTheDocument();
    expect(screen.getByText('Reading files')).toBeInTheDocument();
    expect(screen.getByText('call-read')).toBeInTheDocument();
  });

  it('groups orchestrated blocks by attributed agent', () => {
    renderBlocks([
      { type: 'text', agent_id: 'orchestrator', text: 'Plan ready' },
      { type: 'code', agent_id: 'codex-helper', language: 'ts', code: 'const ok = true;' },
      {
        type: 'tool_call',
        agent_id: 'codex-helper',
        call_id: 'task-a.c-1',
        tool_name: 'write_file',
        arguments: {},
        status: 'ok',
      },
      { type: 'text', agent_id: 'orchestrator', text: 'Summary ready' },
    ]);

    expect(screen.getAllByText('Orchestrator').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Codex Helper').length).toBeGreaterThan(0);
    expect(screen.getByText('Plan ready')).toBeInTheDocument();
    expect(screen.getByText('code:ts:const ok = true;')).toBeInTheDocument();
    expect(screen.getByText('task-a.c-1')).toBeInTheDocument();
    expect(screen.getByText('Summary ready')).toBeInTheDocument();
  });
});
