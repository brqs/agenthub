import type { Agent, ContentBlock, Conversation, Message } from '@/lib/types';

export type TaskStatus = 'pending' | 'running' | 'done' | 'error';

export interface TaskCardBlock {
  type: 'task_card';
  title: string;
  tasks: Array<{
    id: string;
    agent_id: string;
    title: string;
    status: TaskStatus;
  }>;
}

export interface AgentSwitchBlock {
  type: 'agent_switch';
  from_agent: string;
  to_agent: string;
  task: string;
}

export type DemoFileBlock = Extract<ContentBlock, { type: 'file' }> & {
  preview_text?: string;
};

export type DemoWebPreviewBlock = Extract<ContentBlock, { type: 'web_preview' }> & {
  preview_title?: string;
  preview_body?: string;
};

export type DemoContentBlock =
  | Exclude<ContentBlock, { type: 'file' | 'web_preview' }>
  | DemoFileBlock
  | DemoWebPreviewBlock
  | TaskCardBlock
  | AgentSwitchBlock;

export interface DemoMessage extends Omit<Message, 'content'> {
  content: DemoContentBlock[];
}

export interface DemoConversation extends Conversation {
  unread_count?: number;
}

const now = new Date('2026-05-25T10:30:00+08:00');

function minutesAgo(minutes: number): string {
  return new Date(now.getTime() - minutes * 60_000).toISOString();
}

export const mockAgents: Agent[] = [
  {
    id: 'orchestrator',
    name: 'Orchestrator',
    provider: 'custom',
    avatar_url: '',
    capabilities: ['任务拆解', '多 Agent 调度', '结果汇总'],
    system_prompt: '你是 AgentHub 群聊中的任务协调员。',
    config: { model: 'claude-sonnet-4-6', temperature: 0.2 },
    is_builtin: true,
    created_at: minutesAgo(500),
  },
  {
    id: 'claude-code',
    name: 'Claude Code',
    provider: 'claude',
    avatar_url: '',
    capabilities: ['架构设计', '代码生成', '代码审查'],
    system_prompt: null,
    config: { model: 'claude-sonnet-4-6' },
    is_builtin: true,
    created_at: minutesAgo(500),
  },
  {
    id: 'codex-helper',
    name: 'Codex Helper',
    provider: 'openai',
    avatar_url: '',
    capabilities: ['前端实现', '测试补齐', '重构'],
    system_prompt: null,
    config: { model: 'gpt-4o' },
    is_builtin: true,
    created_at: minutesAgo(500),
  },
  {
    id: 'deepseek-assistant',
    name: 'DeepSeek Assistant',
    provider: 'deepseek',
    avatar_url: '',
    capabilities: ['通用问答', '代码辅助', '分析'],
    system_prompt: null,
    config: { model: 'deepseek-v4-flash', temperature: 0.7 },
    is_builtin: true,
    created_at: minutesAgo(500),
  },
  {
    id: 'web-designer',
    name: 'Web Designer',
    provider: 'custom',
    avatar_url: '',
    capabilities: ['UI 设计', '交互打磨', '视觉规范'],
    system_prompt: '你是一位注重产品感的 UI 设计专家。',
    config: { model: 'claude-sonnet-4-6', temperature: 0.7 },
    is_builtin: true,
    created_at: minutesAgo(500),
  },
];

export const mockConversations: DemoConversation[] = [
  {
    id: 'conv-discord-shell',
    title: 'Discord 风格前端壳',
    mode: 'group',
    agent_ids: ['orchestrator', 'claude-code', 'web-designer'],
    is_pinned: true,
    is_archived: false,
    last_message_at: minutesAgo(2),
    last_message_preview: 'Orchestrator: 已拆成布局、组件、流式体验三步。',
    created_at: minutesAgo(180),
  },
  {
    id: 'conv-react-todo',
    title: 'React Todo 组件',
    mode: 'single',
    agent_ids: ['claude-code'],
    is_pinned: true,
    is_archived: false,
    last_message_at: minutesAgo(15),
    last_message_preview: '下面是一个带筛选和本地状态的 Todo 组件。',
    created_at: minutesAgo(240),
  },
  {
    id: 'conv-product-copy',
    title: '产品介绍文案',
    mode: 'single',
    agent_ids: ['web-designer'],
    is_pinned: false,
    is_archived: false,
    last_message_at: minutesAgo(62),
    last_message_preview: '把“多 Agent 协作”讲成一个用户立刻懂的场景。',
    created_at: minutesAgo(360),
    unread_count: 2,
  },
  {
    id: 'conv-demo-flow',
    title: '答辩 Demo 流程',
    mode: 'group',
    agent_ids: ['orchestrator', 'claude-code', 'codex-helper'],
    is_pinned: false,
    is_archived: false,
    last_message_at: minutesAgo(120),
    last_message_preview: '建议用 3 分钟展示单聊、群聊和富媒体产物。',
    created_at: minutesAgo(540),
  },
];

export const mockMessages: Record<string, DemoMessage[]> = {
  'conv-discord-shell': [
    {
      id: 'msg-shell-1',
      conversation_id: 'conv-discord-shell',
      role: 'user',
      agent_id: null,
      content: [{ type: 'text', text: '@Orchestrator 按 Discord 的信息架构，先做 AgentHub 前端桌面 Demo。' }],
      reply_to_id: null,
      status: 'done',
      is_pinned: false,
      created_at: minutesAgo(25),
    },
    {
      id: 'msg-shell-2',
      conversation_id: 'conv-discord-shell',
      role: 'agent',
      agent_id: 'orchestrator',
      content: [
        {
          type: 'task_card',
          title: '前端桌面 Demo 任务规划',
          tasks: [
            { id: 'task-layout', agent_id: 'web-designer', title: '确定四栏布局和深色主题', status: 'done' },
            { id: 'task-chat', agent_id: 'claude-code', title: '实现会话列表、消息区、输入框', status: 'running' },
            { id: 'task-stream', agent_id: 'codex-helper', title: '模拟流式回复并预留 SSE 接口', status: 'pending' },
          ],
        },
        {
          type: 'text',
          text: '我会先把界面拆成模块栏、会话栏、聊天区和右侧 Agent 栏。Mock 数据先跑起来，真实 API 可以从 Hook 层替换。',
        },
      ],
      reply_to_id: 'msg-shell-1',
      status: 'done',
      is_pinned: true,
      created_at: minutesAgo(24),
    },
    {
      id: 'msg-shell-3',
      conversation_id: 'conv-discord-shell',
      role: 'agent',
      agent_id: 'claude-code',
      content: [
        {
          type: 'code',
          language: 'tsx',
          code: `export function AppLayout() {
  return (
    <div className="grid h-screen grid-cols-[64px_280px_1fr_300px]">
      <ModuleRail />
      <ConversationSidebar />
      <ChatWindow />
      <RightAgentPanel />
    </div>
  );
}`,
        },
      ],
      reply_to_id: 'msg-shell-1',
      status: 'done',
      is_pinned: false,
      created_at: minutesAgo(18),
    },
  ],
  'conv-react-todo': [
    {
      id: 'msg-todo-1',
      conversation_id: 'conv-react-todo',
      role: 'user',
      agent_id: null,
      content: [{ type: 'text', text: '用 React 写一个 Todo 组件，最好包含筛选和空状态。' }],
      reply_to_id: null,
      status: 'done',
      is_pinned: false,
      created_at: minutesAgo(40),
    },
    {
      id: 'msg-todo-2',
      conversation_id: 'conv-react-todo',
      role: 'agent',
      agent_id: 'claude-code',
      content: [
        { type: 'text', text: '可以。下面是一个轻量 Todo 组件，状态都放在组件内部，适合直接复制到 Demo。' },
        {
          type: 'code',
          language: 'tsx',
          code: `import { useMemo, useState } from 'react';

type Todo = { id: string; title: string; done: boolean };

export function TodoPanel() {
  const [items, setItems] = useState<Todo[]>([]);
  const [filter, setFilter] = useState<'all' | 'open' | 'done'>('all');

  const visible = useMemo(() => {
    if (filter === 'open') return items.filter((item) => !item.done);
    if (filter === 'done') return items.filter((item) => item.done);
    return items;
  }, [filter, items]);

  return <section>{visible.length ? 'Todo list' : 'No todos yet'}</section>;
}`,
        },
      ],
      reply_to_id: 'msg-todo-1',
      status: 'done',
      is_pinned: false,
      created_at: minutesAgo(38),
    },
  ],
  'conv-product-copy': [
    {
      id: 'msg-copy-1',
      conversation_id: 'conv-product-copy',
      role: 'agent',
      agent_id: 'web-designer',
      content: [
        {
          type: 'text',
          text: '一句话可以写成：AgentHub 让多个 AI 像群聊成员一样协作，把复杂任务拆开、接力完成，并把代码、Diff、预览直接放回聊天流。',
        },
      ],
      reply_to_id: null,
      status: 'done',
      is_pinned: false,
      created_at: minutesAgo(65),
    },
  ],
  'conv-demo-flow': [
    {
      id: 'msg-demo-1',
      conversation_id: 'conv-demo-flow',
      role: 'agent',
      agent_id: 'orchestrator',
      content: [
        { type: 'text', text: 'Demo 建议走“单聊产物 → 群聊编排 → 富媒体展示”三段，观众最容易理解。' },
      ],
      reply_to_id: null,
      status: 'done',
      is_pinned: true,
      created_at: minutesAgo(130),
    },
    {
      id: 'msg-demo-2',
      conversation_id: 'conv-demo-flow',
      role: 'agent',
      agent_id: 'codex-helper',
      content: [
        {
          type: 'diff',
          filename: 'frontend/src/components/chat/MessageInput.tsx',
          before: `function submit() {
  if (!text) return;
  onSend(text);
}`,
          after: `function submit() {
  const value = text.trim();
  if (!value) return;
  onSend(value);
  setText('');
}`,
        },
        {
          type: 'web_preview',
          url: 'https://github.com/brqs/agenthub/pull/1',
          title: 'AgentHub frontend demo pull request',
          description: 'Mock 桌面聊天、Agent 协作流和富媒体消息块的阶段性前端更新。',
          preview_title: 'AgentHub Frontend Demo',
          preview_body:
            '这个预览模拟构建后的桌面 Demo 页面：左侧是 Discord 式导航，中间是多 Agent 聊天流，右侧展示 Agent 上下文。评审可以直接看到任务卡、Agent 切换、代码块、Diff 和文件产物。',
        },
        {
          type: 'file',
          filename: 'agenthub-demo-notes.md',
          url: 'https://github.com/brqs/agenthub',
          size: 18432,
          mime_type: 'text/markdown',
          preview_text: `# AgentHub Demo Notes

## 演示路径

1. 进入聊天页，展示 Discord 式四栏布局。
2. 新建一个群聊会话，默认加入 Orchestrator。
3. 发送 \`@orchestrator 做一次群聊多 Agent 协作演示\`。
4. 展示任务拆解、Agent 切换、代码输出和富媒体产物。

## 当前状态

- Mock API hooks 已就绪。
- Mock SSE 已按真实事件形态实现。
- 富媒体消息块支持 Code、Diff、WebPreview、File。
- 真实 API / SSE 可在 Hook 层替换。
`,
        },
      ],
      reply_to_id: null,
      status: 'done',
      is_pinned: false,
      created_at: minutesAgo(118),
    },
  ],
};

export function getAgent(agentId: string | null | undefined): Agent | undefined {
  if (!agentId) return undefined;
  return mockAgents.find((agent) => agent.id === agentId);
}

export function createMockReply(conversationId: string, agentId: string): DemoMessage {
  return {
    id: `msg-${agentId}-${Date.now()}`,
    conversation_id: conversationId,
    role: 'agent',
    agent_id: agentId,
    content: [{ type: 'text', text: '' }],
    reply_to_id: null,
    status: 'streaming',
    is_pinned: false,
    created_at: new Date().toISOString(),
  };
}
