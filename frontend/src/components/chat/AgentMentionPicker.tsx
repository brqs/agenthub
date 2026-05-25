import { AgentAvatar } from '@/components/agents/AgentAvatar';
import type { Agent } from '@/lib/types';

export function AgentMentionPicker({
  agents,
  query,
  onPick,
}: {
  agents: Agent[];
  query: string;
  onPick: (agent: Agent) => void;
}) {
  const normalized = query.toLowerCase();
  const visibleAgents = agents
    .filter((agent) => agent.name.toLowerCase().includes(normalized) || agent.id.includes(normalized))
    .slice(0, 5);

  if (!visibleAgents.length) return null;

  return (
    <div className="mb-2 w-full max-w-md overflow-hidden rounded-md border border-slate-700 bg-slate-900 shadow-xl">
      {visibleAgents.map((agent) => (
        <button
          key={agent.id}
          type="button"
          onClick={() => onPick(agent)}
          className="flex w-full items-center gap-3 px-3 py-2 text-left transition hover:bg-slate-800"
        >
          <AgentAvatar agent={agent} size="sm" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-white">{agent.name}</div>
            <div className="truncate text-xs text-slate-500">@{agent.id}</div>
          </div>
        </button>
      ))}
    </div>
  );
}

