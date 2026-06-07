import { CheckCircle2, Clock3, HelpCircle, MessageSquare, Route, XCircle } from 'lucide-react';
import type { TurnControlBlock as TurnControlContentBlock } from '@/lib/types';
import { cn } from '@/lib/utils';

const STATUS_LABEL: Record<TurnControlContentBlock['status'], string> = {
  received: '已接收',
  waiting_safe_point: '等待安全点',
  applied: '已应用',
  answered: '已回答',
  cancelled: '已取消',
  expired: '未应用，当前回复已结束',
  failed: '处理失败',
};

export function TurnControlBlock({ block }: { block: TurnControlContentBlock }) {
  const Icon = statusIcon(block.status);
  return (
    <section
      className={cn(
        'rounded-md border px-3 py-2.5 text-sm',
        block.status === 'failed'
          ? 'border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-400/25 dark:bg-rose-950/25 dark:text-rose-100'
          : 'border-slate-200 bg-slate-50 text-slate-800 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-100',
      )}
    >
      <div className="flex min-w-0 items-start gap-2">
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white text-brand shadow-sm dark:bg-slate-950 dark:text-brand-light">
          <Icon className="h-3.5 w-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="font-medium">{controlKindLabel(block.kind)}</span>
            <span className="rounded bg-white px-1.5 py-0.5 text-[11px] text-slate-500 dark:bg-slate-950 dark:text-slate-400">
              {STATUS_LABEL[block.status]}
            </span>
          </div>
          {block.title && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{block.title}</p>}
          {block.body && (
            <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{block.body}</p>
          )}
        </div>
      </div>
    </section>
  );
}

function controlKindLabel(kind: TurnControlContentBlock['kind']): string {
  if (kind === 'guidance') return '引导当前回复';
  if (kind === 'side_chat') return '旁路询问';
  if (kind === 'stop_and_run') return '停止并立即执行';
  return '队列操作';
}

function statusIcon(status: TurnControlContentBlock['status']) {
  if (status === 'applied' || status === 'answered') return CheckCircle2;
  if (status === 'expired' || status === 'cancelled') return XCircle;
  if (status === 'waiting_safe_point') return Clock3;
  if (status === 'failed') return HelpCircle;
  if (status === 'received') return Route;
  return MessageSquare;
}
