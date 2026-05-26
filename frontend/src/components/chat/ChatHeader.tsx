import { GitBranch, MoreHorizontal, PanelLeftOpen, Pin, Search, UserRound, Users } from 'lucide-react';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import type { DemoConversation } from '@/lib/mockData';
import { getAgent } from '@/lib/mockData';

export function ChatHeader({
  conversation,
  sidebarCollapsed = false,
  onExpandSidebar,
}: {
  conversation: DemoConversation;
  sidebarCollapsed?: boolean;
  onExpandSidebar?: () => void;
}) {
  const agents = conversation.agent_ids.map(getAgent).filter((agent) => agent !== undefined);

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
        <div className="min-w-0">
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
        <p className="mt-1 truncate text-xs text-slate-500">
          {conversation.mode === 'group'
            ? `${agents.length} Agents: ${agents.map((agent) => agent.name).join(', ')}`
            : agents[0]?.name}
        </p>
        {conversation.mode === 'group' && (
          <div className="mt-1.5 flex items-center gap-2 text-xs text-slate-500">
            <GitBranch className="h-3.5 w-3.5 text-brand-light" />
            Orchestrator 负责拆解任务，多个 Agent 接力输出产物。
          </div>
        )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex -space-x-2">
          {agents.slice(0, 4).map((agent) => (
            <AgentAvatar key={agent.id} agent={agent} size="sm" />
          ))}
        </div>
        <button type="button" className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white" title="Pin 消息" aria-label="Pin 消息">
          <Pin className="h-4 w-4" />
        </button>
        <button type="button" className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white" title="搜索消息" aria-label="搜索消息">
          <Search className="h-4 w-4" />
        </button>
        <button type="button" className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white" title="更多操作" aria-label="更多操作">
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}
