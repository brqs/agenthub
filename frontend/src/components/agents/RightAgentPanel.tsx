import { useEffect, useMemo, useState } from 'react';
import { Activity, ChevronRight, Files, PanelRight, Pin, ShieldCheck } from 'lucide-react';
import { AgentAvatar } from './AgentAvatar';
import { ArtifactPreview } from '@/components/artifact/ArtifactPreview';
import { WorkspaceFileTree } from '@/components/artifact/WorkspaceFileTree';
import { findLatestTaskCard, getOrchestratorSnapshot } from './orchestratorStatus';
import type { DemoConversation, DemoMessage } from '@/lib/mockData';
import { getAgent } from '@/lib/mockData';
import {
  getFirstWorkspaceFile,
  getMockArtifact,
  getMockWorkspace,
  getWorkspaceFilesFromMessages,
} from '@/lib/mockWorkspace';
import type { Agent } from '@/lib/types';
import { cn } from '@/lib/utils';

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

export function RightAgentPanel({
  conversation,
  messages,
  onSelectPinnedMessage,
}: {
  conversation: DemoConversation;
  messages: DemoMessage[];
  onSelectPinnedMessage?: (messageId: string) => void;
}) {
  const agents = conversation.agent_ids.map(getAgent).filter((agent) => agent !== undefined);
  const pinned = messages.filter((message) => message.is_pinned);
  const snapshot = getOrchestratorSnapshot(conversation, messages);
  const workspace = useMemo(() => getMockWorkspace(conversation.id), [conversation.id]);
  const [selectedArtifactPath, setSelectedArtifactPath] = useState<string | null>(null);
  const touchedFiles = getWorkspaceFilesFromMessages(messages);
  const selectedArtifact = getMockArtifact(conversation.id, selectedArtifactPath);

  useEffect(() => {
    setSelectedArtifactPath(getFirstWorkspaceFile(workspace)?.path ?? null);
  }, [workspace]);

  return (
    <aside className="hidden h-screen w-80 shrink-0 flex-col border-l border-slate-800 bg-slate-900 xl:flex 2xl:w-[22rem]">
      <div className="border-b border-slate-800 p-4 max-[800px]:p-3 [@media(max-height:800px)]:p-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <PanelRight className="h-4 w-4 shrink-0 text-slate-500" />
            <h2 className="truncate text-sm font-semibold text-white">会话上下文</h2>
          </div>
          <span className="shrink-0 rounded-md border border-slate-800 bg-slate-950/70 px-2 py-1 text-xs text-slate-500">
            {agents.length} Agents
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4 scrollbar-thin max-[800px]:p-3 [@media(max-height:800px)]:p-3">
        <section>
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <Activity className="h-3.5 w-3.5" />
            Agents
          </div>
          <div className="space-y-2">
            {agents.map((agent) => {
              const status = getAgentWorkStatus(agent, messages, snapshot.currentAgentId);
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

        <section className="mt-6">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <Files className="h-3.5 w-3.5" />
              Workspace
            </div>
            {workspace && (
              <span className="rounded-md border border-slate-800 bg-slate-950/70 px-2 py-1 text-[11px] text-slate-500">
                {touchedFiles.length} outputs
              </span>
            )}
          </div>

          {workspace ? (
            <div className="space-y-3">
              <div className="rounded-md border border-slate-800 bg-slate-950/60 p-2">
                <div className="mb-1 truncate px-2 py-1 text-[11px] text-slate-600" title={workspace.root}>
                  {workspace.root}
                </div>
                <WorkspaceFileTree
                  nodes={workspace.tree}
                  selectedPath={selectedArtifactPath}
                  onSelectFile={setSelectedArtifactPath}
                />
              </div>
              <ArtifactPreview artifact={selectedArtifact} />
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-slate-800 p-4 text-sm leading-6 text-slate-500">
              当前会话还没有 workspace 产物。真 Agent 调用 write_file 后会在这里出现。
            </div>
          )}
        </section>

        <section className="mt-6">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <Pin className="h-3.5 w-3.5" />
            Pin 消息
          </div>
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

        <section className="mt-6 rounded-md border border-slate-800 bg-slate-950/60 p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-white">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            Mock 模式
          </div>
          <p className="text-sm leading-6 text-slate-500">
            当前 UI 使用本地 Mock 数据，后续会从 Hook 层替换为真实 API 与 SSE。
          </p>
        </section>
      </div>
    </aside>
  );
}
