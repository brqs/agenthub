import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RightAgentPanel } from './RightAgentPanel';
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
  getDeployment: vi.fn(),
  stopDeployment: vi.fn(),
  downloadSourceArchive: vi.fn(),
}));

const conversation: DemoConversation = {
  id: 'conv-panel',
  title: '右栏状态测试',
  mode: 'group',
  agent_ids: ['orchestrator', 'web-designer', 'codex-helper', 'claude-code'],
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
          { id: 'task-2', agent_id: 'web-designer', title: '优化层级', status: 'done' },
          { id: 'task-3', agent_id: 'codex-helper', title: '输出实现', status: 'running' },
          { id: 'task-4', agent_id: 'claude-code', title: '复核风险', status: 'pending' },
        ],
      },
    ],
  },
];

describe('RightAgentPanel', () => {
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
