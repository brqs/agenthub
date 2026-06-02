import { Plus, Search, Sparkles } from 'lucide-react';
import { useMemo, useState } from 'react';
import { AgentCard } from '@/components/agents/AgentCard';
import { AgentCreateDialog } from '@/components/agents/AgentCreateDialog';
import { AgentDetailPanel } from '@/components/agents/AgentDetailPanel';
import { AgentEditDialog } from '@/components/agents/AgentEditDialog';
import { useAgents } from '@/hooks/useAgents';
import { useCreateAgent } from '@/hooks/useCreateAgent';
import { useDeleteAgent } from '@/hooks/useDeleteAgent';
import { useUpdateAgent } from '@/hooks/useUpdateAgent';
import type { Agent } from '@/lib/types';
import { useAgentStore } from '@/stores/agentStore';

export function AgentsPage() {
  const { data: agents } = useAgents();
  const [search, setSearch] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const selectedAgentId = useAgentStore((state) => state.selectedAgentId);
  const setSelectedAgentId = useAgentStore((state) => state.setSelectedAgentId);
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();
  const deleteAgent = useDeleteAgent();

  const filteredAgents = useMemo(() => {
    const normalized = search.trim().toLowerCase();
    if (!normalized) return agents;
    return agents.filter((agent) =>
      [agent.name, agent.provider, ...agent.capabilities]
        .join(' ')
        .toLowerCase()
        .includes(normalized),
    );
  }, [agents, search]);

  const builtin = filteredAgents.filter((agent) => agent.is_builtin);
  const custom = filteredAgents.filter((agent) => !agent.is_builtin);
  const selectedAgent =
    agents.find((agent) => agent.id === selectedAgentId) ?? filteredAgents[0] ?? null;

  return (
    <div className="flex h-full overflow-hidden bg-slate-950">
      <div className="min-w-0 flex-1 overflow-y-auto p-4 scrollbar-thin sm:p-8">
        <div className="mx-auto max-w-6xl">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-light">
                <Sparkles className="h-3.5 w-3.5" />
                AgentHub Registry
              </div>
              <h1 className="mt-2 text-2xl font-bold text-white">Agent 管理</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                管理远端后端中的内置 Agent 与自建 Agent。
              </p>
            </div>
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover"
            >
              <Plus className="h-4 w-4" />
              创建 Agent
            </button>
          </div>

          <div className="mt-8 grid gap-3 md:grid-cols-3">
            <div className="rounded-md border border-slate-800 bg-slate-900 p-4">
              <div className="text-2xl font-semibold text-white">{agents.length}</div>
              <div className="mt-1 text-xs text-slate-500">可用 Agent</div>
            </div>
            <div className="rounded-md border border-slate-800 bg-slate-900 p-4">
              <div className="text-2xl font-semibold text-white">{builtin.length}</div>
              <div className="mt-1 text-xs text-slate-500">内置 Agent</div>
            </div>
            <div className="rounded-md border border-slate-800 bg-slate-900 p-4">
              <div className="text-2xl font-semibold text-white">{custom.length}</div>
              <div className="mt-1 text-xs text-slate-500">我的 Agent</div>
            </div>
          </div>

          <label className="mt-8 flex max-w-md items-center gap-2 rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-400 focus-within:border-brand">
            <Search className="h-4 w-4" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索 Agent、Provider 或能力"
              className="min-w-0 flex-1 bg-transparent text-slate-100 outline-none placeholder:text-slate-600"
            />
          </label>

          {filteredAgents.length === 0 ? (
            <div className="mt-10 rounded-md border border-dashed border-slate-800 bg-slate-900/60 p-10 text-center">
              <div className="text-sm font-medium text-slate-300">没有找到匹配的 Agent</div>
              <p className="mt-2 text-sm text-slate-500">
                换个关键词，或者创建一个新的自建 Agent。
              </p>
            </div>
          ) : (
            <div className="mt-8 space-y-9">
              <AgentSection
                title="我的 Agent"
                agents={custom}
                selectedAgentId={selectedAgent?.id ?? null}
                onSelect={setSelectedAgentId}
                emptyText="还没有自建 Agent，创建一个即可在会话中使用。"
              />
              <AgentSection
                title="内置 Agent"
                agents={builtin}
                selectedAgentId={selectedAgent?.id ?? null}
                onSelect={setSelectedAgentId}
                emptyText="当前筛选条件下没有内置 Agent。"
              />
            </div>
          )}
        </div>
      </div>

      <AgentDetailPanel
        agent={selectedAgent}
        onEdit={setEditingAgent}
        onDelete={async (agent) => {
          if (!window.confirm(`确认删除 ${agent.name}？`)) return;
          await deleteAgent.mutateAsync(agent.id);
        }}
        isDeleting={deleteAgent.isPending}
      />
      <AgentCreateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreate={async (input) => {
          await createAgent.mutateAsync(input);
          setCreateOpen(false);
        }}
      />
      <AgentEditDialog
        open={editingAgent !== null}
        agent={editingAgent}
        isPending={updateAgent.isPending}
        onClose={() => setEditingAgent(null)}
        onUpdate={async (agentId, input) => {
          await updateAgent.mutateAsync({ agentId, input });
          setEditingAgent(null);
        }}
      />
    </div>
  );
}

function AgentSection({
  title,
  agents,
  selectedAgentId,
  onSelect,
  emptyText,
}: {
  title: string;
  agents: ReturnType<typeof useAgents>['data'];
  selectedAgentId: string | null;
  onSelect: (agentId: string) => void;
  emptyText: string;
}) {
  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
        <span className="text-xs text-slate-600">{agents.length}</span>
      </div>
      {agents.length ? (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              active={agent.id === selectedAgentId}
              onSelect={() => onSelect(agent.id)}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-slate-800 bg-slate-900/50 p-6 text-sm text-slate-500">
          {emptyText}
        </div>
      )}
    </section>
  );
}
