import type { Agent, ContentBlock, Conversation, Message } from '@/lib/types';

export type TaskStatus = 'pending' | 'running' | 'done' | 'error';
export type { ProcessBlock } from '@/lib/types';

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
    id: 'conv-markdown-test',
    title: 'Markdown 公式长回复',
    mode: 'single',
    agent_ids: ['deepseek-assistant'],
    is_pinned: false,
    is_archived: false,
    last_message_at: minutesAgo(28),
    last_message_preview: 'DeepSeek Assistant: 中国剩余定理、公式、表格和代码示例。',
    created_at: minutesAgo(300),
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
    title: 'AgentHub 比赛演示',
    mode: 'group',
    agent_ids: ['orchestrator', 'web-designer', 'codex-helper', 'claude-code'],
    is_pinned: false,
    is_archived: false,
    last_message_at: minutesAgo(120),
    last_message_preview: 'Orchestrator: 已拆解为任务规划、界面表达、代码产物和审查建议。',
    created_at: minutesAgo(540),
  },
];

export const markdownQaMessages: DemoMessage[] = [
  {
    id: 'msg-markdown-user-1',
    conversation_id: 'conv-markdown-test',
    role: 'user',
    agent_id: null,
    content: [
      {
        type: 'text',
        text: '@deepseek-assistant 请告诉我中国剩余定理是什么，尽量用 Markdown、公式和例子说明。',
      },
    ],
    reply_to_id: null,
    status: 'done',
    is_pinned: false,
    created_at: minutesAgo(36),
  },
  {
    id: 'msg-markdown-agent-1',
    conversation_id: 'conv-markdown-test',
    role: 'agent',
    agent_id: 'deepseek-assistant',
    content: [
      {
        type: 'text',
        text: String.raw`# 中国剩余定理（CRT）

中国剩余定理（Chinese Remainder Theorem, CRT）解决的是一组同余方程的公共解问题。若模数两两互质，则方程组在模 \(M\) 下有唯一解。

---

## 历史来源

《孙子算经》中有一个经典问题：

> 今有物不知其数，三三数之剩二，五五数之剩三，七七数之剩二，问物几何？

翻译成现代数学语言，就是求整数 \(x\)，满足：

\[
\begin{cases}
x \equiv 2 \pmod{3} \\
x \equiv 3 \pmod{5} \\
x \equiv 2 \pmod{7}
\end{cases}
\]

## 定理的正式表达

设 \(m_1,m_2,\dots,m_k\) 是两两互质的正整数，即 \(\gcd(m_i,m_j)=1\)。对于任意整数 \(a_1,a_2,\dots,a_k\)，同余方程组：

$$
\begin{cases}
x \equiv a_1 \pmod{m_1} \\
x \equiv a_2 \pmod{m_2} \\
\vdots \\
x \equiv a_k \pmod{m_k}
\end{cases}
$$

在模 \(M=m_1m_2\cdots m_k\) 下有唯一解。

## 构造步骤

1. 计算 \(M=\prod_{i=1}^{k}m_i\)。
2. 对每个 \(i\)，令 \(M_i=M/m_i\)。
3. 求 \(M_i\) 在模 \(m_i\) 下的逆元 \(y_i\)，即 \(M_i y_i \equiv 1 \pmod{m_i}\)。
4. 方程组的解为：

$$
x \equiv \sum_{i=1}^{k} a_i M_i y_i \pmod M
$$`,
      },
    ],
    reply_to_id: 'msg-markdown-user-1',
    status: 'done',
    is_pinned: false,
    created_at: minutesAgo(35),
  },
  {
    id: 'msg-markdown-user-2',
    conversation_id: 'conv-markdown-test',
    role: 'user',
    agent_id: null,
    content: [{ type: 'text', text: '继续，把计算过程、表格和代码示例都补上。' }],
    reply_to_id: 'msg-markdown-agent-1',
    status: 'done',
    is_pinned: false,
    created_at: minutesAgo(31),
  },
  {
    id: 'msg-markdown-agent-2',
    conversation_id: 'conv-markdown-test',
    role: 'agent',
    agent_id: 'deepseek-assistant',
    content: [
      {
        type: 'text',
        text: String.raw`## 例子演示

以孙子问题为例：

| i | \(m_i\) | \(a_i\) | \(M_i=M/m_i\) | 逆元 \(y_i\) | 贡献 |
|---|---:|---:|---:|---:|---:|
| 1 | 3 | 2 | 35 | 2 | 140 |
| 2 | 5 | 3 | 21 | 1 | 63 |
| 3 | 7 | 2 | 15 | 1 | 30 |

因此：

$$
x \equiv 140+63+30 \equiv 233 \equiv 23 \pmod{105}
$$

所以最小正整数解是 **23**。

### 校验

- \(23 \div 3 = 7\) 余 \(2\)
- \(23 \div 5 = 4\) 余 \(3\)
- \(23 \div 7 = 3\) 余 \(2\)

### 一个简单实现

~~~ts
function modInverse(a: number, m: number): number {
  for (let x = 1; x < m; x += 1) {
    if ((a * x) % m === 1) return x;
  }
  throw new Error('inverse does not exist');
}

export function chineseRemainder(mods: number[], remainders: number[]) {
  const product = mods.reduce((acc, value) => acc * value, 1);
  const sum = mods.reduce((acc, mod, index) => {
    const partial = product / mod;
    return acc + remainders[index] * partial * modInverse(partial, mod);
  }, 0);

  return ((sum % product) + product) % product;
}
~~~`,
      },
    ],
    reply_to_id: 'msg-markdown-user-2',
    status: 'done',
    is_pinned: true,
    created_at: minutesAgo(30),
  },
  {
    id: 'msg-markdown-user-3',
    conversation_id: 'conv-markdown-test',
    role: 'user',
    agent_id: null,
    content: [{ type: 'text', text: '再加一条长一点的压力测试消息，看看公式、表格、引用在聊天气泡里会不会溢出。' }],
    reply_to_id: 'msg-markdown-agent-2',
    status: 'done',
    is_pinned: false,
    created_at: minutesAgo(29),
  },
  {
    id: 'msg-markdown-agent-3',
    conversation_id: 'conv-markdown-test',
    role: 'agent',
    agent_id: 'deepseek-assistant',
    content: [
      {
        type: 'text',
        text: String.raw`## 长内容与边界测试

下面这条消息故意更长，用来检查聊天气泡在 1280x720、1440x900 和宽屏桌面上的稳定性。它应该像普通 Agent 回复一样在左侧出现，不应该变成文档页面，也不应该撑破聊天主区。

### 长公式

$$
\mathcal{L}(\theta)= -\sum_{i=1}^{n}\sum_{j=1}^{m} y_{ij}\log\left(\frac{\exp(z_{ij}/\tau)}{\sum_{k=1}^{m}\exp(z_{ik}/\tau)}\right)+\lambda\left\|\theta\right\|_2^2+\beta\sum_{t=1}^{T}\left(a_t-\bar a\right)^2
$$

### GFM 表格

| 渲染对象 | 预期表现 | 风险点 |
|---|---|---|
| 二级标题 | 有层级但不夸张 | 字号过大会抢占空间 |
| 行内公式 \(x^2+y^2=z^2\) | 与正文基线协调 | 深色主题下颜色过亮 |
| 块级公式 | 可横向滚动 | 不能撑破气泡 |
| 表格 | 保持边框和对齐 | 窄屏不能溢出主布局 |
| 代码块 | 保留等宽字体 | 内部滚动条不能太抢眼 |

### 流式边界

真实 SSE 中，公式可能被拆成多个 delta。例如先出现 \(\sum_{i=1}^{n}\)，再补上后半段。未闭合片段应降级为文本，不能让页面崩溃。

> 这条测试消息的目的不是展示知识本身，而是让 Markdown 输出像“聊天回复”一样自然出现。`,
      },
    ],
    reply_to_id: 'msg-markdown-user-3',
    status: 'streaming',
    is_pinned: false,
    created_at: minutesAgo(28),
  },
];

export const mockMessages: Record<string, DemoMessage[]> = {
  'conv-markdown-test': markdownQaMessages,
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
      id: 'msg-demo-0',
      conversation_id: 'conv-demo-flow',
      role: 'user',
      agent_id: null,
      content: [
        {
          type: 'text',
          text: '@orchestrator 帮我完成一个带任务拆解、代码产物、Diff 和网页预览的前端开发演示。',
        },
      ],
      reply_to_id: null,
      status: 'done',
      is_pinned: false,
      created_at: minutesAgo(136),
    },
    {
      id: 'msg-demo-1',
      conversation_id: 'conv-demo-flow',
      role: 'agent',
      agent_id: 'orchestrator',
      content: [
        {
          type: 'task_card',
          title: 'AgentHub 比赛演示任务流',
          tasks: [
            { id: 'task-plan-demo', agent_id: 'orchestrator', title: '拆解 3 分钟演示路径', status: 'done' },
            { id: 'task-polish-ui', agent_id: 'web-designer', title: '强调多 Agent 协作状态与界面层级', status: 'done' },
            { id: 'task-output-code', agent_id: 'codex-helper', title: '输出可复制的前端代码与 Diff 产物', status: 'running' },
            { id: 'task-review', agent_id: 'claude-code', title: '检查演示讲述和交互风险', status: 'pending' },
          ],
        },
        {
          type: 'text',
          text: 'Demo 建议走“任务拆解 → Agent 接力 → 富媒体产物 → 结果审查”四段，观众最容易理解 AgentHub 和普通聊天工具的区别。',
        },
        {
          type: 'agent_switch',
          from_agent: 'orchestrator',
          to_agent: 'web-designer',
          task: '先把右侧栏和消息流的协作状态讲清楚。',
        },
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
          type: 'agent_switch',
          from_agent: 'web-designer',
          to_agent: 'codex-helper',
          task: '把界面建议落成可复制的前端代码和变更预览。',
        },
        {
          type: 'text',
          text: '我会先通过工具把产物写进 workspace，再把可读的 Diff、网页预览和演示说明放进聊天流。',
        },
        {
          type: 'tool_call',
          call_id: 'mock-write-demo-html',
          tool_name: 'write_file',
          arguments: {
            path: 'public/demo.html',
            content_preview: '<!doctype html><html lang="zh-CN">...',
          },
          status: 'ok',
          output_preview: 'wrote 4598 bytes to public/demo.html',
          output_truncated: false,
        },
        {
          type: 'tool_call',
          call_id: 'mock-bash-smoke',
          tool_name: 'bash',
          arguments: {
            command: 'pnpm build',
            cwd: '.',
          },
          status: 'ok',
          output_preview: 'vite build completed in 1.42s',
          output_truncated: false,
        },
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
          filename: 'README.md',
          url: '#workspace/README.md',
          size: 18432,
          mime_type: 'text/markdown',
          preview_text: `# AgentHub Demo Notes

## 演示路径

1. 进入聊天页，展示 Discord 式四栏布局。
2. 新建一个群聊会话，默认加入 Orchestrator。
3. 发送 \`@orchestrator 做一次群聊多 Agent 协作演示\`。
4. 展示任务拆解、Agent 切换、代码输出和富媒体产物。

## 当前状态

- API hooks 已接入真实后端。
- SSE 已按真实事件形态接入后端。
- 富媒体消息块支持 Code、Diff、WebPreview、File。
- Workspace 产物可在聊天工作台中预览。
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
