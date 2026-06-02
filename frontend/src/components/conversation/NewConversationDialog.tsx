import { Check, Hash, Users, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import type { Agent } from '@/lib/types';
import { cn } from '@/lib/utils';

export interface NewConversationValue {
  title: string;
  mode: 'single' | 'group';
  agentIds: string[];
}

export function NewConversationDialog({
  open,
  agents,
  isPending,
  onClose,
  onCreate,
}: {
  open: boolean;
  agents: Agent[];
  isPending: boolean;
  onClose: () => void;
  onCreate: (value: NewConversationValue) => void;
}) {
  const [mode, setMode] = useState<'single' | 'group'>('single');
  const [title, setTitle] = useState('');
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>(['claude-code']);

  const canSubmit = useMemo(() => {
    if (!title.trim()) return false;
    if (mode === 'single') return selectedAgentIds.length === 1;
    return selectedAgentIds.length >= 2;
  }, [mode, selectedAgentIds.length, title]);

  if (!open) return null;

  function toggleAgent(agentId: string) {
    setSelectedAgentIds((current) => {
      if (mode === 'single') return [agentId];
      if (current.includes(agentId)) {
        return current.filter((id) => id !== agentId);
      }
      return [...current, agentId];
    });
  }

  function switchMode(nextMode: 'single' | 'group') {
    setMode(nextMode);
    setSelectedAgentIds((current) => {
      if (nextMode === 'single') return [current[0] ?? agents[0]?.id ?? 'claude-code'];
      const withOrchestrator = current.includes('orchestrator')
        ? current
        : ['orchestrator', ...current];
      return Array.from(new Set(withOrchestrator)).slice(0, 4);
    });
  }

  function submit() {
    if (!canSubmit) return;
    onCreate({
      title: title.trim(),
      mode,
      agentIds: selectedAgentIds,
    });
    setTitle('');
    setMode('single');
    setSelectedAgentIds(['claude-code']);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 sm:px-4 sm:py-6 backdrop-blur-sm">
      <section className="flex h-[100dvh] w-full max-w-2xl flex-col overflow-hidden border border-slate-700 bg-slate-900 shadow-2xl sm:max-h-[calc(100dvh-3rem)] sm:rounded-lg">
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-white">新建会话</h2>
            <p className="text-xs text-slate-500">选择单聊或群聊，并指定参与 Agent。</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-800 hover:text-white"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5 scrollbar-thin">
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => switchMode('single')}
              className={cn(
                'flex items-center gap-3 rounded-md border px-4 py-3 text-left',
                mode === 'single'
                  ? 'border-brand bg-brand/10 text-white'
                  : 'border-slate-800 text-slate-400 hover:border-slate-700',
              )}
            >
              <Hash className="h-4 w-4" />
              <div>
                <div className="text-sm font-medium">单聊</div>
                <div className="text-xs text-slate-500">与一个 Agent 对话</div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => switchMode('group')}
              className={cn(
                'flex items-center gap-3 rounded-md border px-4 py-3 text-left',
                mode === 'group'
                  ? 'border-brand bg-brand/10 text-white'
                  : 'border-slate-800 text-slate-400 hover:border-slate-700',
              )}
            >
              <Users className="h-4 w-4" />
              <div>
                <div className="text-sm font-medium">群聊</div>
                <div className="text-xs text-slate-500">由 Orchestrator 协调</div>
              </div>
            </button>
          </div>

          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-500">
              会话标题
            </span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={mode === 'single' ? '例如：React Todo 组件' : '例如：Todo App 协作'}
              className="w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-600 focus:border-brand"
            />
          </label>

          <div>
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              选择 Agent
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {agents.map((agent) => {
                const selected = selectedAgentIds.includes(agent.id);
                return (
                  <button
                    key={agent.id}
                    type="button"
                    onClick={() => toggleAgent(agent.id)}
                    className={cn(
                      'flex items-center gap-3 rounded-md border p-3 text-left transition',
                      selected
                        ? 'border-brand bg-brand/10'
                        : 'border-slate-800 hover:border-slate-700',
                    )}
                  >
                    <AgentAvatar agent={agent} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-white">{agent.name}</div>
                      <div className="truncate text-xs text-slate-500">
                        {agent.capabilities.join(' / ')}
                      </div>
                    </div>
                    {selected && <Check className="h-4 w-4 text-brand-light" />}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <footer className="flex shrink-0 justify-end gap-3 border-t border-slate-800 px-5 pb-[max(env(safe-area-inset-bottom),1rem)] pt-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-4 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            取消
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit || isPending}
            className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isPending ? '创建中...' : '创建会话'}
          </button>
        </footer>
      </section>
    </div>
  );
}
