import { Bot, CheckCircle2, Code2, Edit3, Loader2, MessageSquarePlus, ShieldCheck, Trash2, X } from 'lucide-react';
import { AgentAvatar } from './AgentAvatar';
import type { Agent } from '@/lib/types';
import { cn } from '@/lib/utils';

export function AgentDetailPanel({
  agent,
  onEdit,
  onDelete,
  isDeleting = false,
  presentation = 'desktop',
  onClose,
}: {
  agent: Agent | null;
  onEdit?: (agent: Agent) => void;
  onDelete?: (agent: Agent) => void;
  isDeleting?: boolean;
  presentation?: 'desktop' | 'mobile';
  onClose?: () => void;
}) {
  const panelClassName = cn(
    'h-full shrink-0 overflow-y-auto bg-slate-900 p-5 scrollbar-thin',
    presentation === 'desktop' ? 'hidden w-80 border-l border-slate-800 xl:block' : 'block w-full',
  );

  if (!agent) {
    return (
      <aside className={panelClassName}>
        <div className="flex h-full items-center justify-center rounded-md border border-dashed border-slate-800 text-sm text-slate-500">
          选择一个 Agent 查看详情
        </div>
      </aside>
    );
  }

  return (
    <aside className={panelClassName}>
      {presentation === 'mobile' && (
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-white">Agent 详情</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white"
            aria-label="关闭 Agent 详情"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      <div className="rounded-md border border-slate-800 bg-slate-950/60 p-4">
        <div className="flex items-center gap-3">
          <AgentAvatar agent={agent} size="lg" />
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-white">{agent.name}</h2>
            <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">{agent.provider}</p>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2 text-sm text-slate-300">
          {agent.is_builtin ? (
            <>
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              内置 Agent
            </>
          ) : (
            <>
              <Bot className="h-4 w-4 text-brand-light" />
              我的 Agent
            </>
          )}
        </div>

        {!agent.is_builtin && (
          <div className="mt-4 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => onEdit?.(agent)}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-slate-800 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800 hover:text-white"
            >
              <Edit3 className="h-4 w-4" />
              编辑
            </button>
            <button
              type="button"
              disabled={isDeleting}
              onClick={() => onDelete?.(agent)}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-rose-500/30 px-3 py-2 text-sm text-rose-300 transition hover:bg-rose-500/10 hover:text-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              删除
            </button>
          </div>
        )}
      </div>

      <section className="mt-5">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">能力</h3>
        <div className="flex flex-wrap gap-2">
          {agent.capabilities.map((capability) => (
            <span key={capability} className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300">
              {capability}
            </span>
          ))}
        </div>
      </section>

      <section className="mt-6 rounded-md border border-slate-800 bg-slate-950/60 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-white">
          <Code2 className="h-4 w-4 text-brand-light" />
          运行配置
        </div>
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-xs text-slate-500">Model</dt>
            <dd className="mt-1 text-slate-200">{String(agent.config.model ?? 'default')}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Temperature</dt>
            <dd className="mt-1 text-slate-200">{String(agent.config.temperature ?? 'default')}</dd>
          </div>
        </dl>
      </section>

      <section className="mt-6 rounded-md border border-slate-800 bg-slate-950/60 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-white">
          <MessageSquarePlus className="h-4 w-4 text-emerald-400" />
          接入状态
        </div>
        <div className="space-y-2 text-sm text-slate-400">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            远端 Agent 注册表已连接
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            可加入新建会话
          </div>
        </div>
      </section>

      <section className="mt-6">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">System Prompt</h3>
        <p className="rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm leading-6 text-slate-400">
          {agent.system_prompt ?? '该 Agent 使用默认系统提示。'}
        </p>
      </section>
    </aside>
  );
}
