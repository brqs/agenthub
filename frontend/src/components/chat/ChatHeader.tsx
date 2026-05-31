import {
  GitBranch,
  MoreHorizontal,
  PanelLeftOpen,
  PanelRightOpen,
  Pin,
  Search,
  UserRound,
  Users,
} from 'lucide-react';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import type { DemoConversation } from '@/lib/mockData';
import type { Agent } from '@/lib/types';

export function ChatHeader({
  conversation,
  agents = [],
  sidebarCollapsed = false,
  onExpandSidebar,
  rightPanelOpen = true,
  onOpenRightPanel,
}: {
  conversation: DemoConversation;
  agents?: Agent[];
  sidebarCollapsed?: boolean;
  onExpandSidebar?: () => void;
  rightPanelOpen?: boolean;
  onOpenRightPanel?: () => void;
}) {
  const conversationAgents = conversation.agent_ids
    .map((agentId) => agents.find((agent) => agent.id === agentId))
    .filter((agent) => agent !== undefined);
  const visibleAgents = conversationAgents.slice(0, 3);
  const hiddenAgentCount = Math.max(conversation.agent_ids.length - visibleAgents.length, 0);
  const agentSummary =
    conversation.mode === 'group'
      ? `${conversation.agent_ids.length} Agents · ${
          conversationAgents.map((agent) => agent.name).join(', ') || conversation.agent_ids.join(', ')
        }`
      : conversationAgents[0]?.name ?? conversation.agent_ids[0];

  return (
    <header className="flex min-h-[76px] shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950/70 px-5 py-3 backdrop-blur">
      <div className="flex min-w-0 items-start gap-3">
        {sidebarCollapsed && onExpandSidebar && (
          <button
            type="button"
            onClick={onExpandSidebar}
            className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-slate-800 bg-slate-900 text-slate-400 transition hover:bg-slate-800 hover:text-white focus:outline-none focus:ring-2 focus:ring-brand"
            title="展开会话列表"
            aria-label="展开会话列表"
          >
            <PanelLeftOpen className="h-4 w-4" />
          </button>
        )}
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            {conversation.mode === 'group' ? (
              <Users className="h-4 w-4 text-slate-500" />
            ) : (
              <UserRound className="h-4 w-4 text-slate-500" />
            )}
            <h2 className="truncate text-base font-semibold text-white">{conversation.title}</h2>
            <span className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-xs text-slate-400">
              {conversation.mode === 'group' ? 'Orchestrated' : 'Single Agent'}
            </span>
          </div>
          <p className="truncate text-xs text-slate-500">{agentSummary}</p>
          {conversation.mode === 'group' && (
            <div className="flex items-center gap-2 text-xs text-slate-600">
              <GitBranch className="h-3.5 w-3.5 text-brand-light/80" />
              <span className="truncate">Orchestrator 调度，多 Agent 接力输出。</span>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          className="mr-1 flex items-center rounded-full border border-slate-800 bg-slate-950/70 px-1.5 py-1 transition hover:border-slate-700 hover:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-brand"
          title={agentSummary}
          aria-label="查看会话 Agent"
        >
          <span className="flex -space-x-2">
            {visibleAgents.map((agent) => (
              <AgentAvatar key={agent.id} agent={agent} size="sm" />
            ))}
          </span>
          {hiddenAgentCount > 0 && (
            <span className="ml-2 pr-1 text-xs font-medium text-slate-500">+{hiddenAgentCount}</span>
          )}
        </button>
        <button type="button" className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white" title="Pin 消息" aria-label="Pin 消息">
          <Pin className="h-4 w-4" />
        </button>
        <button type="button" className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white" title="搜索消息" aria-label="搜索消息">
          <Search className="h-4 w-4" />
        </button>
        {!rightPanelOpen && onOpenRightPanel && (
          <button
            type="button"
            onClick={onOpenRightPanel}
            className="hidden rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white xl:inline-flex"
            title="展开工作台"
            aria-label="展开工作台"
          >
            <PanelRightOpen className="h-4 w-4" />
          </button>
        )}
        <button type="button" className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white" title="更多操作" aria-label="更多操作">
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}
