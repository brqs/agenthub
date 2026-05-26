import type { DemoMessage } from './mockData';

export type WorkspaceNode = WorkspaceFileNode | WorkspaceDirectoryNode;

export interface WorkspaceFileNode {
  type: 'file';
  name: string;
  path: string;
  size: number;
  mime_type: string;
}

export interface WorkspaceDirectoryNode {
  type: 'dir';
  name: string;
  path: string;
  children: WorkspaceNode[];
}

export interface MockArtifactFile {
  path: string;
  name: string;
  mime_type: string;
  size: number;
  content: string;
}

export interface MockWorkspace {
  root: string;
  tree: WorkspaceNode[];
  files: Record<string, MockArtifactFile>;
}

const demoHtml = `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>AgentHub Runtime Demo</title>
    <style>
      :root {
        color-scheme: dark;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #020617;
        color: #e2e8f0;
      }

      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background:
          radial-gradient(circle at 20% 20%, rgba(45, 212, 191, 0.18), transparent 30%),
          linear-gradient(135deg, #020617 0%, #111827 52%, #0f172a 100%);
      }

      main {
        width: min(760px, calc(100vw - 32px));
        border: 1px solid rgba(148, 163, 184, 0.25);
        border-radius: 14px;
        background: rgba(15, 23, 42, 0.82);
        box-shadow: 0 24px 80px rgba(0, 0, 0, 0.42);
        padding: 28px;
      }

      .eyebrow {
        color: #5eead4;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }

      h1 {
        margin: 12px 0 10px;
        font-size: clamp(32px, 7vw, 68px);
        line-height: 0.96;
      }

      p {
        max-width: 58ch;
        color: #94a3b8;
        line-height: 1.7;
      }

      .steps {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 10px;
        margin-top: 24px;
      }

      .step {
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 10px;
        background: rgba(2, 6, 23, 0.55);
        padding: 14px;
      }

      .step strong {
        display: block;
        color: #f8fafc;
        font-size: 14px;
      }

      .step span {
        display: block;
        margin-top: 6px;
        color: #94a3b8;
        font-size: 12px;
        line-height: 1.5;
      }

      @media (max-width: 640px) {
        main { padding: 22px; }
        .steps { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <main>
      <div class="eyebrow">Live Artifact Preview</div>
      <h1>AgentHub Demo</h1>
      <p>
        这是一份由 Mock Agent Runtime 写入 workspace 的 HTML 产物。前端可以在右侧文件树中打开它，
        用 iframe 实时预览，并继续让 Agent 基于产物迭代。
      </p>
      <section class="steps">
        <div class="step"><strong>1. Tool call</strong><span>Agent 调用 write_file 写入产物。</span></div>
        <div class="step"><strong>2. Preview</strong><span>ArtifactPreview 读取 workspace 内容。</span></div>
        <div class="step"><strong>3. Iterate</strong><span>用户确认后继续对话式修改。</span></div>
      </section>
    </main>
  </body>
</html>`;

const appTsx = `import { useMemo, useState } from 'react';

const agents = ['Orchestrator', 'Claude Code', 'Codex Helper'];

export function RuntimeDemo() {
  const [active, setActive] = useState(agents[0]);
  const progress = useMemo(() => agents.indexOf(active) + 1, [active]);

  return (
    <section className="rounded-md border border-slate-800 bg-slate-950 p-4">
      <h2 className="text-sm font-semibold text-white">AgentHub Runtime Demo</h2>
      <p className="mt-2 text-sm text-slate-400">
        当前由 {active} 处理 workspace 产物，进度 {progress}/{agents.length}。
      </p>
      <div className="mt-4 flex gap-2">
        {agents.map((agent) => (
          <button key={agent} onClick={() => setActive(agent)}>
            {agent}
          </button>
        ))}
      </div>
    </section>
  );
}`;

const demoNotes = `# AgentHub Runtime Demo

## 演示路径

1. 用户在群聊里 @Orchestrator 提交复杂任务。
2. Orchestrator 拆解任务并切换到 Codex Helper。
3. Codex Helper 调用 \`write_file\` 和 \`bash\`，产出 HTML 与 React 文件。
4. 前端在聊天流中展示 ToolCallBlock，并在右侧 Workspace 中预览产物。

## 前端重点

- ToolCallBlock 让评审看见 Agent 的真实执行过程。
- ArtifactPreview 让产物从聊天文本变成可检查结果。
- 文件树为后续 Monaco 二次编辑和一键部署预留入口。
`;

function file(path: string, mimeType: string, content: string): MockArtifactFile {
  const name = path.split('/').at(-1) ?? path;
  return {
    path,
    name,
    mime_type: mimeType,
    size: new Blob([content]).size,
    content,
  };
}

const demoFiles = {
  'public/demo.html': file('public/demo.html', 'text/html', demoHtml),
  'src/RuntimeDemo.tsx': file('src/RuntimeDemo.tsx', 'text/typescript', appTsx),
  'README.md': file('README.md', 'text/markdown', demoNotes),
};

export const mockWorkspaces: Record<string, MockWorkspace> = {
  'conv-demo-flow': {
    root: '/workspaces/conv-demo-flow',
    files: demoFiles,
    tree: [
      {
        type: 'dir',
        name: 'public',
        path: 'public',
        children: [
          {
            type: 'file',
            name: 'demo.html',
            path: 'public/demo.html',
            size: demoFiles['public/demo.html'].size,
            mime_type: demoFiles['public/demo.html'].mime_type,
          },
        ],
      },
      {
        type: 'dir',
        name: 'src',
        path: 'src',
        children: [
          {
            type: 'file',
            name: 'RuntimeDemo.tsx',
            path: 'src/RuntimeDemo.tsx',
            size: demoFiles['src/RuntimeDemo.tsx'].size,
            mime_type: demoFiles['src/RuntimeDemo.tsx'].mime_type,
          },
        ],
      },
      {
        type: 'file',
        name: 'README.md',
        path: 'README.md',
        size: demoFiles['README.md'].size,
        mime_type: demoFiles['README.md'].mime_type,
      },
    ],
  },
};

function flattenTree(nodes: WorkspaceNode[]): WorkspaceFileNode[] {
  return nodes.flatMap((node) => {
    if (node.type === 'file') return [node];
    return flattenTree(node.children);
  });
}

export function getMockWorkspace(conversationId: string): MockWorkspace | null {
  return mockWorkspaces[conversationId] ?? null;
}

export function getFirstWorkspaceFile(workspace: MockWorkspace | null): WorkspaceFileNode | null {
  if (!workspace) return null;
  return flattenTree(workspace.tree)[0] ?? null;
}

export function getMockArtifact(conversationId: string, path: string | null): MockArtifactFile | null {
  if (!path) return null;
  return mockWorkspaces[conversationId]?.files[path] ?? null;
}

export function getWorkspaceFilesFromMessages(messages: DemoMessage[]): string[] {
  const paths = new Set<string>();
  messages.forEach((message) => {
    message.content.forEach((block) => {
      if (block.type !== 'tool_call') return;
      const path = block.arguments.path;
      if (typeof path === 'string') paths.add(path);
    });
  });
  return Array.from(paths);
}
