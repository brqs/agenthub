import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RightAgentPanel } from './RightAgentPanel';
import * as deploymentsAdapter from '@/lib/adapters/deployments';
import * as workspacesAdapter from '@/lib/adapters/workspaces';
import type { WorkspaceTreeResponse } from '@/lib/adapters/workspaces';
import { DEPLOYMENT_ACTIONS } from '@/components/artifact/deploymentPresentation';
import { mockAgents, type DemoConversation, type DemoMessage } from '@/lib/mockData';

vi.mock('@/lib/adapters/workspaces', () => ({
  getWorkspaceTree: vi.fn().mockResolvedValue({
    root: '/workspaces/conv-panel',
    tree: {
      type: 'directory',
      name: 'conv-panel',
      path: '',
      children: [
        { type: 'file', name: 'demo.html', path: 'demo.html', size: 10, mime_type: 'text/html' },
      ],
    },
  }),
  readWorkspaceFile: vi.fn().mockResolvedValue({
    path: 'demo.html',
    name: 'demo.html',
    size: 10,
    mime_type: 'text/html',
    content: '<h1>Demo</h1>',
  }),
  writeWorkspaceFile: vi.fn(),
}));

vi.mock('@/lib/adapters/deployments', () => ({
  listDeployments: vi.fn().mockResolvedValue({ items: [] }),
  createDeployment: vi.fn().mockResolvedValue({
    id: 'deployment-created',
    conversation_id: 'conv-demo-flow',
    workspace_id: 'workspace-1',
    kind: 'static_site',
    status: 'queued',
    attempt_count: 0,
    logs: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }),
  getDeployment: vi.fn(),
  stopDeployment: vi.fn(),
  downloadSourceArchive: vi.fn(),
}));

const defaultWorkspaceTree: WorkspaceTreeResponse = {
  root: '/workspaces/conv-panel',
  tree: {
    type: 'directory',
    name: 'conv-panel',
    path: '',
    children: [
      { type: 'file', name: 'demo.html', path: 'demo.html', size: 10, mime_type: 'text/html' },
    ],
  },
};

function actionLabel(kind: 'static_site' | 'source_zip' | 'container') {
  return DEPLOYMENT_ACTIONS.find((action) => action.kind === kind)?.label ?? kind;
}

function actionButtonName(kind: 'static_site' | 'source_zip' | 'container') {
  return new RegExp(actionLabel(kind));
}

const conversation: DemoConversation = {
  id: 'conv-panel',
  title: '右栏状态测试',
  mode: 'group',
  agent_ids: ['orchestrator', 'opencode-helper', 'codex-helper', 'claude-code'],
  is_pinned: false,
  is_archived: false,
  last_message_at: new Date().toISOString(),
  created_at: new Date().toISOString(),
};

const messages: DemoMessage[] = [
  {
    id: 'msg-panel',
    conversation_id: conversation.id,
    role: 'agent',
    agent_id: 'orchestrator',
    reply_to_id: null,
    status: 'done',
    is_pinned: true,
    created_at: new Date().toISOString(),
    content: [
      {
        type: 'task_card',
        title: '右栏任务流',
        tasks: [
          { id: 'task-1', agent_id: 'orchestrator', title: '拆解任务', status: 'done' },
          { id: 'task-2', agent_id: 'opencode-helper', title: '优化层级', status: 'done' },
          { id: 'task-3', agent_id: 'codex-helper', title: '输出实现', status: 'running' },
          { id: 'task-4', agent_id: 'claude-code', title: '复核风险', status: 'pending' },
        ],
      },
    ],
  },
];

describe('RightAgentPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspacesAdapter.getWorkspaceTree).mockResolvedValue(defaultWorkspaceTree);
    vi.mocked(workspacesAdapter.readWorkspaceFile).mockResolvedValue({
      path: 'demo.html',
      name: 'demo.html',
      size: 10,
      mime_type: 'text/html',
      content: '<h1>Demo</h1>',
    });
    vi.mocked(deploymentsAdapter.listDeployments).mockResolvedValue({ items: [] });
    vi.mocked(deploymentsAdapter.createDeployment).mockResolvedValue({
      id: 'deployment-created',
      conversation_id: 'conv-demo-flow',
      workspace_id: 'workspace-1',
      kind: 'static_site',
      status: 'queued',
      attempt_count: 0,
      logs: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  });

  function renderPanel(panel: React.ReactNode) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(<QueryClientProvider client={queryClient}>{panel}</QueryClientProvider>);
  }

  it('shows active, done, and idle agent states derived from tasks', () => {
    renderPanel(<RightAgentPanel conversation={conversation} messages={messages} agents={mockAgents} />);
    fireEvent.click(screen.getByRole('button', { name: /Context/ }));

    expect(screen.getAllByText('Codex Helper').length).toBeGreaterThan(0);
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getAllByText('Done')).toHaveLength(2);
    expect(screen.getByText('Idle')).toBeInTheDocument();
  });

  it('keeps the panel header compact and avoids duplicated conversation status', () => {
    renderPanel(<RightAgentPanel conversation={conversation} messages={messages} agents={mockAgents} />);

    expect(screen.getByText('工作台')).toBeInTheDocument();
    expect(screen.getByText('Group')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Workspace/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Context/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Agents$/ })).not.toBeInTheDocument();
    expect(screen.queryByText('群聊协作中')).not.toBeInTheDocument();
  });

  it('shows files returned by the workspace API', async () => {
    renderPanel(
      <RightAgentPanel
        conversation={{ ...conversation, id: 'conv-demo-flow' }}
        agents={mockAgents}
        messages={[
          {
            ...messages[0],
            conversation_id: 'conv-demo-flow',
            content: [
              ...messages[0].content,
              {
                type: 'tool_call',
                call_id: 'call-file',
                tool_name: 'write_file',
                arguments: { path: 'public/demo.html' },
                status: 'ok',
              },
            ],
          },
        ]}
      />,
    );

    expect(await screen.findAllByText('demo.html')).not.toHaveLength(0);
    expect(screen.getByText('1 outputs')).toBeInTheDocument();
  });

  it('keeps the workspace tree visible when only file preview loading fails', async () => {
    vi.mocked(workspacesAdapter.readWorkspaceFile).mockRejectedValue(new Error('file missing'));

    renderPanel(
      <RightAgentPanel
        conversation={{ ...conversation, id: 'conv-demo-flow' }}
        agents={mockAgents}
        messages={messages}
      />,
    );

    expect(await screen.findAllByText('demo.html')).not.toHaveLength(0);
    expect(await screen.findByText('文件预览加载失败，请稍后重试。', {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.queryByText('Workspace 加载失败，请稍后重试。')).not.toBeInTheDocument();
    expect(screen.getByText('发布历史')).toBeInTheDocument();
  });

  it('keeps the last workspace tree visible when background refresh fails', async () => {
    vi.mocked(workspacesAdapter.getWorkspaceTree).mockRejectedValue(new Error('tree unavailable'));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    queryClient.setQueryData(['workspace-tree', 'conv-demo-flow'], {
      root: '/workspaces/conv-demo-flow',
      tree: {
        type: 'directory',
        name: 'conv-demo-flow',
        path: '',
        children: [
          { type: 'file', name: 'cached.html', path: 'cached.html', size: 10, mime_type: 'text/html' },
        ],
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <RightAgentPanel
          conversation={{ ...conversation, id: 'conv-demo-flow' }}
          agents={mockAgents}
          messages={messages}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findAllByText('cached.html')).not.toHaveLength(0);
    expect(
      await screen.findByText('Workspace 刷新失败，已保留上一次可用内容。', {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Workspace 加载失败，请稍后重试。')).not.toBeInTheDocument();
    expect(screen.getByText('发布历史')).toBeInTheDocument();
  });

  it('shows the main workspace error only when no tree data exists', async () => {
    vi.mocked(workspacesAdapter.getWorkspaceTree).mockRejectedValue(new Error('tree unavailable'));

    renderPanel(
      <RightAgentPanel
        conversation={{ ...conversation, id: 'conv-demo-flow' }}
        agents={mockAgents}
        messages={messages}
      />,
    );

    expect(
      await screen.findByText('Workspace 加载失败，请稍后重试。', {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(screen.getByText('发布历史')).toBeInTheDocument();
  });

  it('does not reuse the selected file path after switching conversations', async () => {
    vi.mocked(workspacesAdapter.getWorkspaceTree).mockImplementation(async (conversationId) => ({
      root: `/workspaces/${conversationId}`,
      tree: {
        type: 'directory',
        name: conversationId,
        path: '',
        children:
          conversationId === 'conv-a'
            ? [{ type: 'file', name: 'a.html', path: 'a.html', size: 10, mime_type: 'text/html' }]
            : [{ type: 'file', name: 'b.html', path: 'b.html', size: 10, mime_type: 'text/html' }],
      },
    }));
    vi.mocked(workspacesAdapter.readWorkspaceFile).mockImplementation(async (conversationId, path) => ({
      path,
      name: path,
      size: 10,
      mime_type: 'text/html',
      content: `<h1>${conversationId}:${path}</h1>`,
    }));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <RightAgentPanel
          conversation={{ ...conversation, id: 'conv-a' }}
          agents={mockAgents}
          messages={messages}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findAllByText('a.html')).not.toHaveLength(0);
    await waitFor(() => {
      expect(workspacesAdapter.readWorkspaceFile).toHaveBeenCalledWith('conv-a', 'a.html');
    });

    rerender(
      <QueryClientProvider client={queryClient}>
        <RightAgentPanel
          conversation={{ ...conversation, id: 'conv-b' }}
          agents={mockAgents}
          messages={messages}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findAllByText('b.html')).not.toHaveLength(0);
    await waitFor(() => {
      expect(workspacesAdapter.readWorkspaceFile).toHaveBeenCalledWith('conv-b', 'b.html');
    });
    expect(workspacesAdapter.readWorkspaceFile).not.toHaveBeenCalledWith('conv-b', 'a.html');
  });

  it('creates a static deployment from the selected workspace HTML file', async () => {
    renderPanel(
      <RightAgentPanel
        conversation={{ ...conversation, id: 'conv-demo-flow' }}
        agents={mockAgents}
        messages={messages}
      />,
    );

    expect(await screen.findAllByText('demo.html')).not.toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: actionButtonName('static_site') }));

    await waitFor(() => {
      expect(deploymentsAdapter.createDeployment).toHaveBeenCalledWith('conv-demo-flow', {
        kind: 'static_site',
        entry_path: 'demo.html',
      });
    });
  });

  it('uses root index.html for static deployment when a non-html file is selected', async () => {
    vi.mocked(workspacesAdapter.getWorkspaceTree).mockResolvedValue({
      root: '/workspaces/conv-panel',
      tree: {
        type: 'directory',
        name: 'conv-panel',
        path: '',
        children: [
          { type: 'file', name: 'README.md', path: 'README.md', size: 75, mime_type: 'text/markdown' },
          { type: 'file', name: 'index.html', path: 'index.html', size: 20, mime_type: 'text/html' },
          { type: 'file', name: 'app.js', path: 'app.js', size: 30, mime_type: 'text/javascript' },
        ],
      },
    });
    vi.mocked(workspacesAdapter.readWorkspaceFile).mockResolvedValue({
      path: 'README.md',
      name: 'README.md',
      size: 75,
      mime_type: 'text/markdown',
      content: '# README',
    });

    renderPanel(
      <RightAgentPanel
        conversation={{ ...conversation, id: 'conv-demo-flow' }}
        agents={mockAgents}
        messages={messages}
      />,
    );

    expect(await screen.findAllByText('README.md')).not.toHaveLength(0);
    expect(screen.getByRole('button', { name: actionButtonName('static_site') })).toHaveAttribute(
      'title',
      '静态入口：index.html',
    );
    fireEvent.click(screen.getByRole('button', { name: actionButtonName('static_site') }));

    await waitFor(() => {
      expect(deploymentsAdapter.createDeployment).toHaveBeenCalledWith('conv-demo-flow', {
        kind: 'static_site',
        entry_path: 'index.html',
      });
    });
  });

  it('disables static deployment when no html entry exists', async () => {
    vi.mocked(workspacesAdapter.getWorkspaceTree).mockResolvedValue({
      root: '/workspaces/conv-panel',
      tree: {
        type: 'directory',
        name: 'conv-panel',
        path: '',
        children: [
          { type: 'file', name: 'README.md', path: 'README.md', size: 75, mime_type: 'text/markdown' },
        ],
      },
    });

    renderPanel(
      <RightAgentPanel
        conversation={{ ...conversation, id: 'conv-demo-flow' }}
        agents={mockAgents}
        messages={messages}
      />,
    );

    expect(await screen.findAllByText('README.md')).not.toHaveLength(0);
    const staticButton = screen.getByRole('button', { name: actionButtonName('static_site') });

    expect(staticButton).toBeDisabled();
    expect(staticButton).toHaveAttribute('title', '需要 index.html 或 HTML 入口文件');
  });

  it('creates a source zip and shows success feedback', async () => {
    vi.mocked(deploymentsAdapter.createDeployment).mockResolvedValue({
      id: 'source-created',
      conversation_id: 'conv-demo-flow',
      workspace_id: 'workspace-1',
      kind: 'source_zip',
      status: 'published',
      attempt_count: 0,
      download_url: '/api/v1/workspaces/conv-demo-flow/deployments/source-created/download',
      logs: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    renderPanel(
      <RightAgentPanel
        conversation={{ ...conversation, id: 'conv-demo-flow' }}
        agents={mockAgents}
        messages={messages}
      />,
    );

    expect(await screen.findAllByText('demo.html')).not.toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: actionButtonName('source_zip') }));

    await waitFor(() => {
      expect(deploymentsAdapter.createDeployment).toHaveBeenCalledWith('conv-demo-flow', {
        kind: 'source_zip',
      });
    });
    expect(await screen.findByText(/可在发布历史下载/)).toBeInTheDocument();
  });

  it('shows a download button for published source zip history items', async () => {
    const createObjectUrl = vi.fn().mockReturnValue('blob:source-zip');
    const revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectUrl,
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectUrl,
    });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    vi.mocked(deploymentsAdapter.downloadSourceArchive).mockResolvedValue(new Blob(['zip']));
    vi.mocked(deploymentsAdapter.listDeployments).mockResolvedValue({
      items: [
        {
          id: 'source-created',
          conversation_id: 'conv-demo-flow',
          workspace_id: 'workspace-1',
          kind: 'source_zip',
          status: 'published',
          attempt_count: 0,
          download_url: '/api/v1/workspaces/conv-demo-flow/deployments/source-created/download',
          size_bytes: 191,
          logs: [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
    });

    renderPanel(
      <RightAgentPanel
        conversation={{ ...conversation, id: 'conv-demo-flow' }}
        agents={mockAgents}
        messages={messages}
      />,
    );

    const downloadButton = await screen.findByRole('button', { name: '下载源码包' });
    fireEvent.click(downloadButton);

    await waitFor(() => {
      expect(deploymentsAdapter.downloadSourceArchive).toHaveBeenCalledWith(
        'conv-demo-flow',
        'source-created',
        '/api/v1/workspaces/conv-demo-flow/deployments/source-created/download',
      );
    });
  });

  it('allows container deployment requests even before Dockerfile exists', async () => {
    renderPanel(
      <RightAgentPanel
        conversation={{ ...conversation, id: 'conv-demo-flow' }}
        agents={mockAgents}
        messages={messages}
      />,
    );

    expect(await screen.findAllByText('demo.html')).not.toHaveLength(0);
    const containerButton = screen.getByRole('button', { name: actionButtonName('container') });

    expect(containerButton).not.toBeDisabled();
    expect(containerButton).toHaveAttribute('title', '后端将检查 Dockerfile 和容器部署能力');
    fireEvent.click(containerButton);

    await waitFor(() => {
      expect(deploymentsAdapter.createDeployment).toHaveBeenCalledWith('conv-demo-flow', {
        kind: 'container',
      });
    });
  });

  it('creates a container deployment when Dockerfile exists', async () => {
    vi.mocked(workspacesAdapter.getWorkspaceTree).mockResolvedValue({
      root: '/workspaces/conv-panel',
      tree: {
        type: 'directory',
        name: 'conv-panel',
        path: '',
        children: [
          { type: 'file', name: 'Dockerfile', path: 'Dockerfile', size: 25, mime_type: 'text/plain' },
          { type: 'file', name: 'index.html', path: 'index.html', size: 20, mime_type: 'text/html' },
        ],
      },
    });
    renderPanel(
      <RightAgentPanel
        conversation={{ ...conversation, id: 'conv-demo-flow' }}
        agents={mockAgents}
        messages={messages}
      />,
    );

    expect(await screen.findAllByText('Dockerfile')).not.toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: actionButtonName('container') }));

    await waitFor(() => {
      expect(deploymentsAdapter.createDeployment).toHaveBeenCalledWith('conv-demo-flow', {
        kind: 'container',
      });
    });
  });

  it('shows a readable notice when container deployment is not supported', async () => {
    vi.mocked(deploymentsAdapter.createDeployment).mockResolvedValueOnce({
      id: 'container-not-supported',
      conversation_id: 'conv-demo-flow',
      workspace_id: 'workspace-1',
      kind: 'container',
      status: 'not_supported',
      attempt_count: 0,
      error: 'Container deployment is not enabled',
      logs: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    renderPanel(
      <RightAgentPanel
        conversation={{ ...conversation, id: 'conv-demo-flow' }}
        agents={mockAgents}
        messages={messages}
      />,
    );

    fireEvent.click(await screen.findByRole('button', { name: actionButtonName('container') }));

    await waitFor(() => {
      expect(deploymentsAdapter.createDeployment).toHaveBeenCalledWith('conv-demo-flow', {
        kind: 'container',
      });
    });
    expect(await screen.findByText(/容器部署请求已创建，但未发布成功/)).toBeInTheDocument();
    expect(screen.getByText(/Container deployment is not enabled/)).toBeInTheDocument();
  });

  it('keeps agents and pinned messages in the context tab', () => {
    renderPanel(<RightAgentPanel conversation={conversation} messages={messages} agents={mockAgents} />);

    fireEvent.click(screen.getByRole('button', { name: /Context/ }));

    expect(screen.getByText('Agents in group')).toBeInTheDocument();
    expect(screen.getAllByText('Codex Helper').length).toBeGreaterThan(0);
    expect(screen.getByText('Pin 消息')).toBeInTheDocument();
    expect(screen.getByText('1 pinned')).toBeInTheDocument();
    expect(screen.getByText('富媒体内容')).toBeInTheDocument();
  });
});
