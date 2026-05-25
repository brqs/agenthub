import { Bot, CheckCircle2, Code2, MessageSquarePlus, ShieldCheck } from 'lucide-react';
import { AgentAvatar } from './AgentAvatar';
import type { Agent } from '@/lib/types';

export function AgentDetailPanel({ agent }: { agent: Agent | null }) {
  if (!agent) {
    return (
      <aside className="hidden w-80 shrink-0 border-l border-slate-800 bg-slate-900 p-5 xl:block">
        <div className="flex h-full items-center justify-center rounded-md border border-dashed border-slate-800 text-sm text-slate-500">
          选择一个 Agent 查看详情
        </div>
      </aside>
    );
  }

  return (
    <aside className="hidden h-screen w-80 shrink-0 overflow-y-auto border-l border-slate-800 bg-slate-900 p-5 scrollbar-thin xl:block">
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
            Mock Agent 列表可用
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
