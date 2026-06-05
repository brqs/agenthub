import { useEffect, useMemo, useState, type PointerEvent as ReactPointerEvent } from 'react';
import {
  Activity,
  Box,
  ChevronRight,
  Files,
  GripVertical,
  PanelRight,
  PanelRightClose,
  Pin,
  RefreshCw,
} from 'lucide-react';
import { AgentAvatar } from './AgentAvatar';
import { ArtifactPreview, type PreviewArtifactFile } from '@/components/artifact/ArtifactPreview';
import { DeploymentHistory } from '@/components/artifact/DeploymentHistory';
import {
  DEPLOYMENT_ACTIONS,
  DEPLOYMENT_KIND_LABELS,
  type DeploymentKind,
} from '@/components/artifact/deploymentPresentation';
import { WorkspaceFileTree, type WorkspaceNode } from '@/components/artifact/WorkspaceFileTree';
import { findLatestTaskCard, getOrchestratorSnapshot } from './orchestratorStatus';
import type { DemoConversation, DemoMessage } from '@/lib/mockData';
import { getWorkspaceFilesFromMessages } from '@/lib/workspaceFiles';
import { useCreateDeployment } from '@/hooks/useDeployments';
import { useWorkspaceFile, useWorkspaceTree, useWriteWorkspaceFile } from '@/hooks/useWorkspace';
import type { Agent, WorkspaceDeploymentRequest } from '@/lib/types';
import { extractApiError } from '@/lib/api';
import { cn } from '@/lib/utils';
import { RIGHT_PANEL_DEFAULT_WIDTH } from '@/stores/uiStore';

type AgentWorkStatus = 'active' | 'done' | 'idle';

function getAgentWorkStatus(agent: Agent, messages: DemoMessage[], activeAgentId: string): AgentWorkStatus {
  if (agent.id === activeAgentId) return 'active';

  const taskCard = findLatestTaskCard(messages);
  const ownedTasks = taskCard?.tasks.filter((task) => task.agent_id === agent.id) ?? [];
  if (ownedTasks.length > 0 && ownedTasks.every((task) => task.status === 'done')) return 'done';

  return 'idle';
}

const STATUS_LABEL: Record<AgentWorkStatus, string> = {
  active: 'Active',
  done: 'Done',
  idle: 'Idle',
};

const STATUS_CLASS: Record<AgentWorkStatus, string> = {
  active: 'border-brand/30 bg-brand/15 text-brand-light',
  done: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300',
  idle: 'border-slate-700 bg-slate-800 text-slate-500',
};

type RightPanelTab = 'context' | 'workspace';
type DeploymentNoticeTone = 'success' | 'warning' | 'error';
type DeploymentNotice = {
  kind: DeploymentKind;
  tone: DeploymentNoticeTone;
  text: string;
};
type DeploymentActionIntent = {
  payload: WorkspaceDeploymentRequest;
  detail: string;
  disabledReason: string | null;
};
type DeploymentActionIntents = Record<DeploymentKind, DeploymentActionIntent>;

const TAB_META: Record<RightPanelTab, { label: string; icon: typeof Activity }> = {
  context: { label: 'Context', icon: Activity },
  workspace: { label: 'Workspace', icon: Files },
};

function getDefaultTab(hasWorkspace: boolean): RightPanelTab {
  if (hasWorkspace) return 'workspace';
  return 'context';
}

export function RightAgentPanel({
  conversation,
  messages,
  agents = [],
  width = RIGHT_PANEL_DEFAULT_WIDTH,
  onWidthChange = () => undefined,
  onCollapse = () => undefined,
  onSelectPinnedMessage,
  presentation = 'desktop',
}: {
  conversation: DemoConversation;
  messages: DemoMessage[];
  agents?: Agent[];
  width?: number;
  onWidthChange?: (width: number) => void;
  onCollapse?: () => void;
  onSelectPinnedMessage?: (messageId: string) => void;
  presentation?: 'desktop' | 'mobile';
}) {
  const conversationAgents = conversation.agent_ids
    .map((agentId) => agents.find((agent) => agent.id === agentId))
    .filter((agent) => agent !== undefined);
  const pinned = messages.filter((message) => message.is_pinned);
  const snapshot = getOrchestratorSnapshot(conversation, messages, agents);
  const [activeTab, setActiveTab] = useState<RightPanelTab>(() => getDefaultTab(true));
  const touchedFiles = getWorkspaceFilesFromMessages(messages);

  useEffect(() => {
    setActiveTab(getDefaultTab(true));
  }, [conversation.id]);

  return (
    <aside
      className={cn(
        'relative h-full shrink-0 flex-col border-l border-slate-800 bg-slate-900',
        presentation === 'desktop' ? 'hidden xl:flex' : 'flex w-full',
      )}
      style={presentation === 'desktop' ? { width } : undefined}
    >
      {presentation === 'desktop' && <ResizeHandle width={width} onWidthChange={onWidthChange} />}
      <div className="p-4 pb-3 max-[800px]:p-3 [@media(max-height:800px)]:p-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <PanelRight className="h-4 w-4 shrink-0 text-slate-500" />
            <h2 className="truncate text-sm font-semibold text-white">工作台</h2>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="rounded-md border border-slate-800 bg-slate-950/70 px-2 py-1 text-xs text-slate-500" title={conversation.title}>
              {conversation.mode === 'group' ? 'Group' : 'Single'}
            </span>
            <button
              type="button"
              onClick={onCollapse}
              className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-800 bg-slate-950 text-slate-400 transition hover:bg-slate-800 hover:text-white focus:outline-none focus:ring-2 focus:ring-brand"
              title="收起工作台"
              aria-label="收起工作台"
            >
              <PanelRightClose className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-1 rounded-md border border-slate-800 bg-slate-950/70 p-1">
          {(Object.keys(TAB_META) as RightPanelTab[]).map((tab) => {
            const Icon = TAB_META[tab].icon;
            return (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={cn(
                  'flex min-w-0 items-center justify-center gap-1.5 rounded px-2 py-1.5 text-xs font-medium transition',
                  activeTab === tab
                    ? 'bg-brand/20 text-brand-light shadow-sm shadow-black/20'
                    : 'text-slate-500 hover:bg-slate-800 hover:text-slate-200',
                )}
              >
                <Icon className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{TAB_META[tab].label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4 scrollbar-thin max-[800px]:p-3 [@media(max-height:800px)]:p-3">
        {activeTab === 'workspace' && (
          <RealWorkspacePanel conversationId={conversation.id} touchedFilesCount={touchedFiles.length} />
        )}
        {activeTab === 'context' && (
          <ContextPanel
            agents={conversationAgents}
            messages={messages}
            activeAgentId={snapshot.currentAgentId}
            pinned={pinned}
            onSelectPinnedMessage={onSelectPinnedMessage}
          />
        )}
      </div>
    </aside>
  );
}

function ResizeHandle({
  width,
  onWidthChange,
}: {
  width: number;
  onWidthChange: (width: number) => void;
}) {
  function startResize(event: ReactPointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;

    function handleMove(moveEvent: PointerEvent) {
      onWidthChange(startWidth - (moveEvent.clientX - startX));
    }

    function stopResize() {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', stopResize);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', stopResize, { once: true });
  }

  return (
    <button
      type="button"
      onPointerDown={startResize}
      className="group absolute inset-y-0 left-0 z-10 hidden w-2 -translate-x-1 cursor-col-resize items-center justify-center text-slate-600 transition hover:bg-brand/10 hover:text-brand-light xl:flex"
      title="调整工作台宽度"
      aria-label="调整工作台宽度"
    >
      <GripVertical className="h-4 w-4 opacity-0 transition group-hover:opacity-100" />
    </button>
  );
}

function PanelHeader({
  icon: Icon,
  title,
  meta,
}: {
  icon: typeof Activity;
  title: string;
  meta?: string;
}) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        <Icon className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">{title}</span>
      </div>
      {meta && (
        <span className="shrink-0 rounded-md border border-slate-800 bg-slate-950/70 px-2 py-1 text-[11px] text-slate-500">
          {meta}
        </span>
      )}
    </div>
  );
}

function AgentsPanel({
  agents,
  messages,
  activeAgentId,
}: {
  agents: Agent[];
  messages: DemoMessage[];
  activeAgentId: string;
}) {
  return (
    <section>
      <PanelHeader icon={Activity} title="Agents in group" meta={`${agents.length} total`} />
      <div className="space-y-2">
        {agents.map((agent) => {
          const status = getAgentWorkStatus(agent, messages, activeAgentId);
          return (
            <div
              key={agent.id}
              className="rounded-md border border-slate-800 bg-slate-950/60 p-3 transition hover:border-slate-700 hover:bg-slate-950/80"
            >
              <div className="flex items-center gap-3">
                <AgentAvatar agent={agent} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-white" title={`${agent.name} · ${agent.provider}`}>
                    {agent.name}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-slate-600">{agent.provider}</div>
                </div>
                <span className={cn('rounded-md border px-2 py-1 text-xs', STATUS_CLASS[status])}>
                  {STATUS_LABEL[status]}
                </span>
                <ChevronRight className="h-4 w-4 text-slate-600" />
              </div>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {agent.capabilities.slice(0, 3).map((capability) => (
                  <span key={capability} className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                    {capability}
                  </span>
                ))}
                {agent.capabilities.length > 3 && (
                  <span className="rounded bg-slate-800/70 px-2 py-0.5 text-xs text-slate-500">
                    +{agent.capabilities.length - 3}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function WorkspacePanel({
  workspace,
  conversationId,
  isLoading,
  workspaceError,
  artifactError,
  touchedFilesCount,
  selectedArtifactPath,
  selectedArtifact,
  onSelectArtifact,
  onRetryWorkspace,
  onRetryArtifact,
  onSaveArtifact,
  isSavingArtifact = false,
}: {
  workspace: { root: string; tree: WorkspaceNode[] } | null;
  conversationId: string;
  isLoading: boolean;
  workspaceError: unknown;
  artifactError?: unknown;
  touchedFilesCount: number;
  selectedArtifactPath: string | null;
  selectedArtifact: PreviewArtifactFile | null;
  onSelectArtifact: (path: string) => void;
  onRetryWorkspace: () => void;
  onRetryArtifact: () => void;
  onSaveArtifact?: (path: string, content: string | Blob, mimeType: string) => Promise<void> | void;
  isSavingArtifact?: boolean;
}) {
  const createDeployment = useCreateDeployment(conversationId);
  const [activeDeploymentKind, setActiveDeploymentKind] = useState<DeploymentKind | null>(null);
  const [deploymentNotice, setDeploymentNotice] = useState<DeploymentNotice | null>(null);
  const actionIntents = useMemo(
    () => buildDeploymentActionIntents(workspace?.tree ?? [], selectedArtifactPath),
    [workspace?.tree, selectedArtifactPath],
  );

  useEffect(() => {
    if (deploymentNotice?.tone !== 'success') return undefined;
    const timeoutId = window.setTimeout(() => setDeploymentNotice(null), 4_000);
    return () => window.clearTimeout(timeoutId);
  }, [deploymentNotice]);

  function createRelease(kind: DeploymentKind) {
    const intent = actionIntents[kind];
    if (intent.disabledReason) {
      setDeploymentNotice({
        kind,
        tone: 'warning',
        text: `${DEPLOYMENT_KIND_LABELS[kind]}：${intent.disabledReason}`,
      });
      return;
    }
    createDeployment.reset();
    setDeploymentNotice(null);
    setActiveDeploymentKind(kind);
    createDeployment.mutate(intent.payload, {
      onSuccess: (deployment) => {
        if (deployment.status === 'failed' || deployment.status === 'not_supported') {
          setDeploymentNotice({
            kind,
            tone: 'warning',
            text: `${DEPLOYMENT_KIND_LABELS[kind]}请求已创建，但未发布成功：${deployment.error || deployment.status}`,
          });
          return;
        }
        const target =
          deployment.kind === 'source_zip'
            ? '可在发布历史下载'
            : deployment.url
              ? `已生成 URL：${deployment.url}`
              : '可在发布历史查看';
        setDeploymentNotice({
          kind,
          tone: 'success',
          text: `${DEPLOYMENT_KIND_LABELS[kind]}已完成，${target}`,
        });
      },
      onError: (error) => {
        setDeploymentNotice({
          kind,
          tone: 'error',
          text: `${DEPLOYMENT_KIND_LABELS[kind]}请求失败：${extractApiError(error)}`,
        });
      },
      onSettled: () => {
        setActiveDeploymentKind(null);
      },
    });
  }

  return (
    <section className="space-y-5">
      <div>
      <PanelHeader icon={Box} title="Workspace" meta={`${touchedFilesCount} outputs`} />

      {isLoading ? (
        <div className="rounded-md border border-slate-800 p-4 text-sm text-slate-500">
          正在加载 workspace...
        </div>
      ) : workspaceError ? (
        <div className="space-y-3 rounded-md border border-red-500/30 bg-red-950/20 p-4 text-sm leading-6 text-red-100">
          <p>Workspace 加载失败，请稍后重试。</p>
          <button
            type="button"
            onClick={onRetryWorkspace}
            className="inline-flex items-center gap-1.5 rounded-md border border-red-400/40 px-2.5 py-1.5 text-xs font-medium text-red-50 transition hover:bg-red-400/10"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            重试
          </button>
        </div>
      ) : workspace ? (
        <div className="space-y-3">
          <div className="rounded-md border border-slate-800 bg-slate-950/60 p-2">
            <div className="mb-1 truncate px-2 py-1 text-[11px] text-slate-600" title={workspace.root}>
              {workspace.root}
            </div>
            <WorkspaceFileTree
              nodes={workspace.tree}
              selectedPath={selectedArtifactPath}
              onSelectFile={onSelectArtifact}
            />
          </div>
          {artifactError ? (
            <div className="space-y-3 rounded-md border border-red-500/30 bg-red-950/20 p-4 text-sm leading-6 text-red-100">
              <p>文件预览加载失败，请稍后重试。</p>
              <button
                type="button"
                onClick={onRetryArtifact}
                className="inline-flex items-center gap-1.5 rounded-md border border-red-400/40 px-2.5 py-1.5 text-xs font-medium text-red-50 transition hover:bg-red-400/10"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                重试
              </button>
            </div>
          ) : (
            <ArtifactPreview
              artifact={selectedArtifact}
              onSave={onSaveArtifact}
              isSaving={isSavingArtifact}
            />
          )}
          <DeploymentReleaseActions
            intents={actionIntents}
            pendingKind={activeDeploymentKind}
            onCreate={createRelease}
          />
          {deploymentNotice && (
            <p
              className={cn(
                'rounded-md border px-3 py-2 text-xs leading-5',
                deploymentNotice.tone === 'success'
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/25 dark:bg-emerald-950/20 dark:text-emerald-200'
                  : deploymentNotice.tone === 'warning'
                    ? 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-400/25 dark:bg-amber-950/20 dark:text-amber-200'
                    : 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-400/25 dark:bg-rose-950/20 dark:text-rose-200',
              )}
            >
              {deploymentNotice.text}
            </p>
          )}
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-slate-800 p-4 text-sm leading-6 text-slate-500">
          当前会话还没有 workspace 产物。真 Agent 调用 write_file 后会在这里出现。
        </div>
      )}
      </div>
      <DeploymentHistory conversationId={conversationId} />
    </section>
  );
}

function DeploymentReleaseActions({
  intents,
  pendingKind,
  onCreate,
}: {
  intents: DeploymentActionIntents;
  pendingKind: DeploymentKind | null;
  onCreate: (kind: DeploymentKind) => void;
}) {
  const staticDetail = intents.static_site.detail;
  return (
    <section className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
      <div className="mb-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">发布操作</div>
        <p className="mt-1 text-xs leading-5 text-slate-500">
          前端只创建发布请求，部署、打包和容器运行由后端平台 tool 完成。
        </p>
        <p className="mt-1 truncate text-[11px] text-slate-600" title={staticDetail}>
          {staticDetail}
        </p>
      </div>
      <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3">
        {DEPLOYMENT_ACTIONS.map((action) => {
          const Icon = action.icon;
          const intent = intents[action.kind];
          const isPending = pendingKind === action.kind;
          const disabled = isPending || intent.disabledReason !== null;
          return (
            <button
              key={action.kind}
              type="button"
              onClick={() => onCreate(action.kind)}
              disabled={disabled}
              title={intent.disabledReason ?? intent.detail}
              className="rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-left transition hover:border-brand/40 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span className="flex items-center gap-2 text-xs font-medium text-slate-100">
                <Icon className={cn('h-3.5 w-3.5 text-brand-light', isPending && 'animate-spin')} />
                {action.label}
              </span>
              <span className="mt-1 block text-[11px] leading-4 text-slate-500">
                {intent.disabledReason ?? action.description}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function RealWorkspacePanel({
  conversationId,
  touchedFilesCount,
}: {
  conversationId: string;
  touchedFilesCount: number;
}) {
  const workspaceQuery = useWorkspaceTree(conversationId);
  const workspace = useMemo(() => {
    if (!workspaceQuery.data) return null;
    const rootNode = workspaceQuery.data.tree;
    return {
      root: workspaceQuery.data.root,
      tree: rootNode.type === 'directory' ? rootNode.children : [rootNode],
    };
  }, [workspaceQuery.data]);
  const [selectedArtifactPath, setSelectedArtifactPath] = useState<string | null>(null);
  const workspaceFiles = useMemo(
    () => (workspace ? flattenFiles(workspace.tree) : []),
    [workspace],
  );
  const activeArtifactPath =
    selectedArtifactPath && workspaceFiles.some((file) => file.path === selectedArtifactPath)
      ? selectedArtifactPath
      : null;
  const artifactQuery = useWorkspaceFile(conversationId, activeArtifactPath);
  const writeWorkspaceFile = useWriteWorkspaceFile(conversationId);
  const realTouchedFilesCount = workspace ? workspaceFiles.length : touchedFilesCount;

  useEffect(() => {
    setSelectedArtifactPath(null);
  }, [conversationId]);

  useEffect(() => {
    if (workspaceFiles.length === 0) {
      if (selectedArtifactPath !== null) setSelectedArtifactPath(null);
      return;
    }
    if (selectedArtifactPath && workspaceFiles.some((file) => file.path === selectedArtifactPath)) return;
    setSelectedArtifactPath(workspaceFiles[0].path);
  }, [workspaceFiles, selectedArtifactPath]);

  return (
    <WorkspacePanel
      workspace={workspace}
      conversationId={conversationId}
      isLoading={workspaceQuery.isLoading}
      workspaceError={workspaceQuery.error}
      artifactError={artifactQuery.error}
      touchedFilesCount={realTouchedFilesCount}
      selectedArtifactPath={activeArtifactPath}
      selectedArtifact={artifactQuery.data ?? null}
      onSelectArtifact={setSelectedArtifactPath}
      onRetryWorkspace={() => {
        setSelectedArtifactPath(null);
        void workspaceQuery.refetch();
      }}
      onRetryArtifact={() => {
        void artifactQuery.refetch();
      }}
      onSaveArtifact={(path, content, mimeType) =>
        writeWorkspaceFile.mutateAsync({ path, content, mimeType })
      }
      isSavingArtifact={writeWorkspaceFile.isPending}
    />
  );
}

function flattenFiles(nodes: WorkspaceNode[]): Array<Extract<WorkspaceNode, { type: 'file' }>> {
  return nodes.flatMap((node) => {
    if (node.type === 'file') return [node];
    return flattenFiles(node.children);
  });
}

function buildDeploymentActionIntents(
  nodes: WorkspaceNode[],
  selectedPath: string | null,
): DeploymentActionIntents {
  const files = flattenFiles(nodes);
  const staticEntry = resolveStaticEntry(files, selectedPath);
  const dockerfile = files.find((file) => file.path === 'Dockerfile');
  return {
    static_site: {
      payload: staticEntry ? { kind: 'static_site', entry_path: staticEntry.path } : { kind: 'static_site' },
      detail: staticEntry ? `静态入口：${staticEntry.path}` : '未找到 HTML 入口文件',
      disabledReason: staticEntry ? null : '需要 index.html 或 HTML 入口文件',
    },
    source_zip: {
      payload: { kind: 'source_zip' },
      detail: files.length ? '导出当前 workspace 源码包' : 'workspace 暂无文件',
      disabledReason: null,
    },
    container: {
      payload: { kind: 'container' },
      detail: dockerfile ? '容器入口：Dockerfile' : '缺少 Dockerfile',
      disabledReason: dockerfile ? null : '需要 Dockerfile 才能容器部署',
    },
  };
}

function resolveStaticEntry(
  files: Array<Extract<WorkspaceNode, { type: 'file' }>>,
  selectedPath: string | null,
) {
  if (selectedPath && isHtmlPath(selectedPath)) {
    const selected = files.find((file) => file.path === selectedPath);
    if (selected) return selected;
  }
  return (
    files.find((file) => file.path.toLowerCase() === 'index.html') ??
    files.find((file) => isHtmlPath(file.path)) ??
    null
  );
}

function isHtmlPath(path: string): boolean {
  return /\.html?$/i.test(path);
}

function ContextPanel({
  agents,
  messages,
  activeAgentId,
  pinned,
  onSelectPinnedMessage,
}: {
  agents: Agent[];
  messages: DemoMessage[];
  activeAgentId: string;
  pinned: DemoMessage[];
  onSelectPinnedMessage?: (messageId: string) => void;
}) {
  return (
    <div className="space-y-6">
      <AgentsPanel agents={agents} messages={messages} activeAgentId={activeAgentId} />

      <section>
        <PanelHeader icon={Pin} title="Pin 消息" meta={`${pinned.length} pinned`} />
        {pinned.length ? (
          <div className="space-y-2">
            {pinned.map((message) => (
              <button
                key={message.id}
                type="button"
                onClick={() => onSelectPinnedMessage?.(message.id)}
                className="block max-h-[4.75rem] w-full overflow-hidden rounded-md border border-transparent bg-slate-950/60 p-3 text-left text-xs leading-5 text-slate-400 transition hover:border-brand/30 hover:bg-slate-950 hover:text-slate-200"
              >
                {message.content[0]?.type === 'text' ? message.content[0].text : '富媒体内容'}
              </button>
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-slate-800 p-4 text-sm text-slate-500">
            暂无 Pin 消息
          </div>
        )}
      </section>

    </div>
  );
}
