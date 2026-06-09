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
    .filter(
      (agent) => agent.name.toLowerCase().includes(normalized) || agent.id.includes(normalized),
    )
    .slice(0, 5);

  if (!visibleAgents.length) return null;

  return (
    <div className="mb-2 max-h-56 w-full max-w-md overflow-y-auto rounded-md border border-slate-300 bg-white shadow-xl scrollbar-thin dark:border-slate-700 dark:bg-slate-900">
      {visibleAgents.map((agent) => (
        <button
          key={agent.id}
          type="button"
          onClick={() => onPick(agent)}
          className="flex w-full items-center gap-3 px-3 py-2 text-left transition hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          <AgentAvatar agent={agent} size="sm" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-slate-950 dark:text-white">
              {agent.name}
            </div>
            <div className="truncate text-xs text-slate-600 dark:text-slate-500">@{agent.id}</div>
          </div>
        </button>
      ))}
    </div>
  );
}
