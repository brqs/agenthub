import { Plus, Search } from 'lucide-react';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import { mockAgents } from '@/lib/mockData';

export function AgentsPage() {
  const builtin = mockAgents.filter((agent) => agent.is_builtin);

  return (
    <div className="h-screen overflow-y-auto bg-slate-950 p-8 scrollbar-thin">
      <div className="mx-auto max-w-6xl">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Agent 管理</h1>
            <p className="mt-1 text-sm text-slate-500">
              管理内置 Agent 与自建 Agent，后续将接入真实 Agent CRUD API。
            </p>
          </div>
          <button
            type="button"
            className="flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover"
          >
            <Plus className="h-4 w-4" />
            创建 Agent
          </button>
        </div>

        <label className="mt-8 flex max-w-md items-center gap-2 rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-400">
          <Search className="h-4 w-4" />
          <input
            placeholder="搜索 Agent"
            className="min-w-0 flex-1 bg-transparent text-slate-100 outline-none placeholder:text-slate-600"
          />
        </label>

        <section className="mt-8">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
            内置 Agent
          </h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {builtin.map((agent) => (
              <article
                key={agent.id}
                className="rounded-md border border-slate-800 bg-slate-900 p-5 shadow-sm"
              >
                <div className="flex items-center gap-3">
                  <AgentAvatar agent={agent} size="lg" />
                  <div className="min-w-0">
                    <h3 className="truncate text-base font-semibold text-white">{agent.name}</h3>
                    <p className="text-sm text-slate-500">{agent.provider}</p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {agent.capabilities.map((capability) => (
                    <span
                      key={capability}
                      className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300"
                    >
                      {capability}
                    </span>
                  ))}
                </div>
                <div className="mt-5 rounded bg-slate-950 px-3 py-2 text-xs text-slate-500">
                  model: {String(agent.config.model ?? 'default')}
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

