import { MoreHorizontal, Pin, Search, Users } from 'lucide-react';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import type { DemoConversation } from '@/lib/mockData';
import { getAgent } from '@/lib/mockData';

export function ChatHeader({ conversation }: { conversation: DemoConversation }) {
  const agents = conversation.agent_ids.map(getAgent).filter((agent) => agent !== undefined);

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950/70 px-5 backdrop-blur">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {conversation.mode === 'group' && <Users className="h-4 w-4 text-slate-500" />}
          <h2 className="truncate text-base font-semibold text-white">{conversation.title}</h2>
        </div>
        <p className="mt-1 truncate text-xs text-slate-500">
          {conversation.mode === 'group'
            ? `${agents.length} Agents: ${agents.map((agent) => agent.name).join(', ')}`
            : agents[0]?.name}
        </p>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex -space-x-2">
          {agents.slice(0, 4).map((agent) => (
            <AgentAvatar key={agent.id} agent={agent} size="sm" />
          ))}
        </div>
        <button type="button" className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white">
          <Pin className="h-4 w-4" />
        </button>
        <button type="button" className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white">
          <Search className="h-4 w-4" />
        </button>
        <button type="button" className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white">
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}

