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
import { useState } from 'react';
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
  onOpenConversationList,
  onOpenWorkspace,
}: {
  conversation: DemoConversation;
  agents?: Agent[];
  sidebarCollapsed?: boolean;
  onExpandSidebar?: () => void;
  rightPanelOpen?: boolean;
  onOpenRightPanel?: () => void;
  onOpenConversationList?: () => void;
  onOpenWorkspace?: () => void;
}) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const conversationAgents = conversation.agent_ids
    .map((agentId) => agents.find((agent) => agent.id === agentId))
    .filter((agent) => agent !== undefined);
  const visibleAgents = conversationAgents.slice(0, 3);
  const hiddenAgentCount = Math.max(conversation.agent_ids.length - visibleAgents.length, 0);
  const agentSummary =
    conversation.mode === 'group'
      ? `${conversation.agent_ids.length} Agents · ${
          conversationAgents.map((agent) => agent.name).join(', ') ||
          conversation.agent_ids.join(', ')
        }`
      : (conversationAgents[0]?.name ?? conversation.agent_ids[0]);

  return (
    <header className="native-chat-header relative flex shrink-0 items-center justify-between border-b border-slate-200 bg-white/85 px-3 pb-2 backdrop-blur dark:border-slate-800 dark:bg-slate-950/70 sm:px-5 sm:pb-3">
      <div className="flex min-w-0 items-start gap-3">
        {onOpenConversationList && (
          <button
            type="button"
            onClick={onOpenConversationList}
            className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-brand dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white md:hidden"
            title="打开会话列表"
            aria-label="打开会话列表"
          >
            <PanelLeftOpen className="h-4 w-4" />
          </button>
        )}
        {sidebarCollapsed && onExpandSidebar && (
          <button
            type="button"
            onClick={onExpandSidebar}
            className="mt-0.5 hidden h-8 w-8 shrink-0 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-brand dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white md:flex"
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
            <h2 className="truncate text-base font-semibold text-slate-950 dark:text-white">
              {conversation.title}
            </h2>
            <span className="hidden rounded-md border border-slate-300 bg-slate-50 px-2 py-1 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 sm:inline-flex">
              {conversation.mode === 'group' ? 'Orchestrated' : 'Single Agent'}
            </span>
          </div>
          <p className="truncate text-xs text-slate-600 dark:text-slate-500">{agentSummary}</p>
          {conversation.mode === 'group' && (
            <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-600">
              <GitBranch className="h-3.5 w-3.5 text-brand dark:text-brand-light/80" />
              <span className="truncate">Orchestrator 调度，多 Agent 接力输出。</span>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          className="mr-1 hidden items-center rounded-full border border-slate-300 bg-white px-1.5 py-1 transition hover:border-slate-400 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-brand dark:border-slate-800 dark:bg-slate-950/70 dark:hover:border-slate-700 dark:hover:bg-slate-900 sm:flex"
          title={agentSummary}
          aria-label="查看会话 Agent"
        >
          <span className="flex -space-x-2">
            {visibleAgents.map((agent) => (
              <AgentAvatar key={agent.id} agent={agent} size="sm" />
            ))}
          </span>
          {hiddenAgentCount > 0 && (
            <span className="ml-2 pr-1 text-xs font-medium text-slate-600 dark:text-slate-500">
              +{hiddenAgentCount}
            </span>
          )}
        </button>
        <button
          type="button"
          className="hidden rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white sm:inline-flex"
          title="Pin 消息"
          aria-label="Pin 消息"
        >
          <Pin className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="hidden rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white sm:inline-flex"
          title="搜索消息"
          aria-label="搜索消息"
        >
          <Search className="h-4 w-4" />
        </button>
        {onOpenWorkspace && (
          <button
            type="button"
            onClick={onOpenWorkspace}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white xl:hidden"
            title="打开工作台"
            aria-label="打开工作台"
          >
            <PanelRightOpen className="h-4 w-4" />
          </button>
        )}
        {!rightPanelOpen && onOpenRightPanel && (
          <button
            type="button"
            onClick={onOpenRightPanel}
            className="hidden rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white xl:inline-flex"
            title="展开工作台"
            aria-label="展开工作台"
          >
            <PanelRightOpen className="h-4 w-4" />
          </button>
        )}
        <button
          type="button"
          onClick={() => setMobileMenuOpen((open) => !open)}
          className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
          title="更多操作"
          aria-label="更多操作"
          aria-expanded={mobileMenuOpen}
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
      {mobileMenuOpen && (
        <div className="native-chat-header-menu absolute right-3 z-30 w-64 rounded-md border border-slate-300 bg-white p-3 text-sm shadow-xl dark:border-slate-700 dark:bg-slate-900 sm:hidden">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            会话 Agent
          </div>
          <p className="mt-2 text-sm leading-5 text-slate-700 dark:text-slate-300">
            {agentSummary}
          </p>
          {onOpenWorkspace && (
            <button
              type="button"
              onClick={() => {
                setMobileMenuOpen(false);
                onOpenWorkspace();
              }}
              className="mt-3 flex w-full items-center gap-2 rounded-md bg-slate-100 px-3 py-2 text-left text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-200"
              aria-label="从更多菜单打开工作台"
            >
              <PanelRightOpen className="h-4 w-4" />
              打开工作台
            </button>
          )}
        </div>
      )}
    </header>
  );
}
