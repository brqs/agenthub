import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react';
import type { TaskCardBlock as TaskCardBlockData, TaskStatus } from '@/lib/mockData';
import { mockAgents } from '@/lib/mockData';
import type { Agent } from '@/lib/types';
import { cn } from '@/lib/utils';

const STATUS_ICON: Record<TaskStatus, React.ComponentType<{ className?: string }>> = {
  pending: Circle,
  running: Loader2,
  done: CheckCircle2,
  error: XCircle,
};

const STATUS_CLASS: Record<TaskStatus, string> = {
  pending: 'text-slate-500',
  running: 'animate-spin text-amber-400',
  done: 'text-emerald-400',
  error: 'text-red-400',
};

export function TaskCardBlock({
  block,
  agents = mockAgents,
}: {
  block: TaskCardBlockData;
  agents?: Agent[];
}) {
  return (
    <div className="my-3 min-w-0 rounded-md border border-slate-700 bg-slate-900/80 p-4">
      <div className="mb-3 text-sm font-semibold text-white">{block.title}</div>
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
