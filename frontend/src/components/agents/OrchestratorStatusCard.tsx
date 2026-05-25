import { GitBranch, Route, Sparkles } from 'lucide-react';
import { getOrchestratorSnapshot } from './orchestratorStatus';
import type { DemoConversation, DemoMessage } from '@/lib/mockData';
import { cn } from '@/lib/utils';

export function OrchestratorStatusCard({
  conversation,
  messages,
}: {
  conversation: DemoConversation;
  messages: DemoMessage[];
}) {
  const snapshot = getOrchestratorSnapshot(conversation, messages);
  const progress =
    snapshot.totalTasks > 0 ? `${snapshot.doneTasks} / ${snapshot.totalTasks}` : '暂无任务卡';

  return (
    <section className="rounded-md border border-brand/25 bg-brand/10 p-3">
      <div className="mb-2.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-light">
        <Sparkles className="h-3.5 w-3.5" />
        Collaboration
      </div>
      <div className="space-y-2.5">
        <div>
          <div className="text-sm font-semibold text-white">{snapshot.modeLabel}</div>
            <div className="mt-0.5 text-xs text-slate-500">
            当前阶段：<span className="text-slate-300">{snapshot.stage}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-md border border-slate-800 bg-slate-950/70 p-2.5">
            <div className="mb-1 flex items-center gap-1.5 text-xs text-slate-500">
              <Route className="h-3.5 w-3.5" />
              接力 Agent
            </div>
            <div className="truncate text-sm font-medium text-slate-100">
              {snapshot.currentAgentName}
            </div>
          </div>
          <div className="rounded-md border border-slate-800 bg-slate-950/70 p-2.5">
            <div className="mb-1 flex items-center gap-1.5 text-xs text-slate-500">
              <GitBranch className="h-3.5 w-3.5" />
              任务进度
            </div>
            <div className="text-sm font-medium text-slate-100">{progress}</div>
          </div>
        </div>

        {snapshot.switchLabel && (
          <div className="truncate rounded-md bg-slate-950/60 px-3 py-2 text-xs text-slate-400">
            最近接力：<span className="text-slate-200">{snapshot.switchLabel}</span>
          </div>
        )}

        <div
          className={cn(
            'rounded-md px-3 py-2 text-xs leading-5',
            snapshot.runningTaskTitle
              ? 'bg-amber-400/10 text-amber-100'
              : 'bg-slate-950/60 text-slate-500',
          )}
        >
          {snapshot.runningTaskTitle ?? '等待下一次群聊任务拆解。'}
        </div>
      </div>
    </section>
  );
}
