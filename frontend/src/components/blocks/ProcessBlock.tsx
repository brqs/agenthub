import { AlertTriangle, CheckCircle2, CircleDashed, Clock3, ListChecks } from 'lucide-react';
import type { ProcessBlock as ProcessBlockData, ProcessStep } from '@/lib/types';
import { cn } from '@/lib/utils';

const STATUS_META = {
  running: {
    label: '进行中',
    className:
      'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-400/25 dark:bg-sky-400/10 dark:text-sky-200',
    icon: Clock3,
  },
  done: {
    label: '已完成',
    className:
      'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/25 dark:bg-emerald-400/10 dark:text-emerald-200',
    icon: CheckCircle2,
  },
  partial: {
    label: '部分完成',
    className:
      'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200',
    icon: AlertTriangle,
  },
  error: {
    label: '需要注意',
    className:
      'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-400/25 dark:bg-rose-400/10 dark:text-rose-200',
    icon: AlertTriangle,
  },
} as const;

const STEP_STATUS_META = {
  done: { className: 'text-emerald-600 dark:text-emerald-300', icon: CheckCircle2 },
  running: { className: 'text-sky-600 dark:text-sky-300', icon: Clock3 },
  error: { className: 'text-rose-600 dark:text-rose-300', icon: AlertTriangle },
  skipped: { className: 'text-slate-500 dark:text-slate-400', icon: CircleDashed },
} as const;

const KIND_LABELS: Record<ProcessStep['kind'], string> = {
  routing: '路由',
  planning: '计划',
  dispatch: '执行',
  tool: '工具',
  review: 'Review',
  evaluation: '验收',
  workflow: '工作流',
  deployment: '部署',
  artifact: '产物',
  repair: '修复',
  summary: '总结',
};

export function ProcessBlock({ block }: { block: ProcessBlockData }) {
  const meta = STATUS_META[block.status];
  const StatusIcon = meta.icon;

  return (
    <section className="my-3 min-w-0 overflow-hidden rounded-md border border-slate-300 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950/70">
      <div className="flex min-w-0 items-center gap-3 border-b border-slate-200 px-3 py-2.5 dark:border-slate-800">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-brand/25 bg-brand/10 text-brand dark:text-brand-light">
          <ListChecks className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-slate-950 dark:text-white">
            {block.title}
          </div>
          {block.summary && (
            <div className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
              {block.summary}
            </div>
          )}
        </div>
        <span
          className={cn(
            'inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-xs',
            meta.className,
          )}
        >
          <StatusIcon className="h-3.5 w-3.5" />
          {meta.label}
        </span>
      </div>
      <div className="grid min-w-0 gap-2 px-3 py-3">
        {block.steps.map((step, index) => {
          const stepMeta = STEP_STATUS_META[step.status];
          const StepIcon = stepMeta.icon;
          return (
            <div
              key={step.id ?? `${step.kind}-${index}-${step.label}`}
              className="grid min-w-0 grid-cols-[1rem_minmax(0,1fr)] gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-900/70"
            >
              <StepIcon className={cn('mt-0.5 h-4 w-4', stepMeta.className)} />
              <div className="min-w-0">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="min-w-0 break-words text-sm font-medium text-slate-900 dark:text-slate-100">
                    {step.label}
                  </span>
                  <span className="shrink-0 rounded border border-slate-300 bg-white px-1.5 py-0.5 text-[11px] text-slate-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-400">
                    {KIND_LABELS[step.kind]}
                  </span>
                </div>
                {step.detail && (
                  <div className="mt-1 break-words text-xs leading-5 text-slate-600 dark:text-slate-400">
                    {step.detail}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
