import { CheckCircle2, Circle, CircleDashed, Loader2, XCircle } from 'lucide-react';
import type { TaskCardBlock as TaskCardBlockData, TaskStatus } from '@/lib/mockData';
import type { Agent } from '@/lib/types';
import { cn } from '@/lib/utils';

const STATUS_ICON: Record<TaskStatus, React.ComponentType<{ className?: string }>> = {
  pending: Circle,
  running: Loader2,
  done: CheckCircle2,
  error: XCircle,
  interrupted: CircleDashed,
};

const STATUS_CLASS: Record<TaskStatus, string> = {
  pending: 'text-slate-500',
  running: 'animate-spin text-amber-400',
  done: 'text-emerald-400',
  error: 'text-red-400',
  interrupted: 'text-slate-400',
};

export function TaskCardBlock({
  block,
  agents = [],
}: {
  block: TaskCardBlockData;
  agents?: Agent[];
}) {
  const doneCount = block.tasks.filter((task) => task.status === 'done').length;
  const runningTask = block.tasks.find((task) => task.status === 'running');
  const hasError = block.tasks.some((task) => task.status === 'error');
  const hasInterrupted = block.tasks.some((task) => task.status === 'interrupted');
  const stage = hasError
    ? '执行失败'
    : hasInterrupted
      ? '已打断'
      : runningTask
        ? `正在调度 @${agents.find((item) => item.id === runningTask.agent_id)?.name ?? runningTask.agent_id}`
        : doneCount === block.tasks.length && block.tasks.length > 0
          ? '执行结果已汇总'
          : '等待调度';

  return (
    <div className="my-3 min-w-0 rounded-md border border-brand/30 bg-brand/10 p-4 shadow-[0_0_0_1px_rgba(99,102,241,0.08)]">
      <div className="mb-3 flex min-w-0 items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-white">{block.title}</div>
          <div className="mt-1 truncate text-xs text-slate-400">{stage}</div>
        </div>
        <span className="shrink-0 rounded bg-slate-950/70 px-2 py-1 text-xs text-slate-300">
          {doneCount}/{block.tasks.length}
        </span>
      </div>
      <div className="space-y-2">
        {block.tasks.map((task, index) => {
          const Icon = STATUS_ICON[task.status];
          const agent = agents.find((item) => item.id === task.agent_id);
          return (
            <div
              key={task.id}
              className={cn(
                'task-row-enter flex min-w-0 items-center gap-3 rounded bg-slate-950/70 px-3 py-2 transition-colors',
                task.status === 'running' && 'task-running bg-amber-400/10',
                task.status === 'done' && 'task-done',
                task.status === 'interrupted' && 'bg-slate-400/10',
              )}
            >
              <Icon className={`h-4 w-4 ${STATUS_CLASS[task.status]}`} />
              <span className="text-xs text-slate-500">{index + 1}</span>
              <span className="min-w-0 flex-1 truncate text-sm text-slate-200">{task.title}</span>
              <span className="max-w-36 truncate rounded bg-slate-800 px-2 py-1 text-xs text-slate-400">
                @{agent?.name ?? task.agent_id}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
