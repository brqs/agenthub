import { ChevronRight, ShieldCheck, Wrench } from 'lucide-react';
import { AgentAvatar } from './AgentAvatar';
import type { Agent } from '@/lib/types';
import { cn } from '@/lib/utils';

export function AgentCard({
  agent,
  active,
  onSelect,
}: {
  agent: Agent;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'group w-full rounded-md border p-4 text-left transition',
        active
          ? 'border-brand bg-brand/10 shadow-lg shadow-brand/10'
          : 'border-slate-800 bg-slate-900 hover:border-slate-700 hover:bg-slate-800/60',
      )}
    >
      <div className="flex items-center gap-3">
        <AgentAvatar agent={agent} size="lg" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-white">{agent.name}</h3>
            {agent.is_builtin ? (
              <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
            ) : (
              <Wrench className="h-3.5 w-3.5 shrink-0 text-brand-light" />
            )}
          </div>
          <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">{agent.provider}</p>
        </div>
        <ChevronRight className="h-4 w-4 text-slate-600 transition group-hover:text-slate-300" />
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {agent.capabilities.slice(0, 4).map((capability) => (
          <span key={capability} className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300">
            {capability}
          </span>
        ))}
      </div>

      <div className="mt-4 truncate rounded bg-slate-950 px-3 py-2 text-xs text-slate-500">
        model: {String(agent.config.model ?? 'default')}
      </div>
    </button>
  );
}
