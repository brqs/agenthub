import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Clock3, Terminal } from 'lucide-react';
import { useState } from 'react';
import type { ToolCallBlock as ToolCallBlockType } from '@/lib/types';
import { cn } from '@/lib/utils';

const STATUS_META = {
  pending: {
    label: 'Running',
    className: 'border-amber-400/20 bg-amber-400/10 text-amber-200',
    icon: Clock3,
  },
  ok: {
    label: 'Done',
    className: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300',
    icon: CheckCircle2,
  },
  error: {
    label: 'Error',
    className: 'border-rose-400/20 bg-rose-400/10 text-rose-300',
    icon: AlertTriangle,
  },
} as const;

function formatJson(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2);
}

export function ToolCallBlock({ block }: { block: ToolCallBlockType }) {
  const [open, setOpen] = useState(block.status !== 'ok');
  const meta = STATUS_META[block.status];
  const StatusIcon = meta.icon;
  const ToggleIcon = open ? ChevronDown : ChevronRight;

  return (
    <section className="overflow-hidden rounded-md border border-slate-800 bg-slate-950/70">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full min-w-0 items-center gap-3 px-3 py-2.5 text-left transition hover:bg-slate-900/70"
      >
        <ToggleIcon className="h-4 w-4 shrink-0 text-slate-500" />
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-slate-800 bg-slate-900 text-brand-light">
          <Terminal className="h-4 w-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-white">{block.tool_name}</span>
          <span className="block truncate text-xs text-slate-500">{block.call_id}</span>
        </span>
        <span className={cn('inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-xs', meta.className)}>
          <StatusIcon className="h-3.5 w-3.5" />
          {meta.label}
        </span>
      </button>

      {open && (
        <div className="border-t border-slate-800 px-3 py-3">
          <div className="grid gap-3">
            <div>
              <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">Arguments</div>
              <pre className="max-h-44 overflow-auto rounded-md border border-slate-800 bg-slate-950 p-3 text-xs leading-5 text-slate-300 scrollbar-thin">
                {formatJson(block.arguments)}
              </pre>
            </div>

            {(block.output_preview || block.error_code) && (
              <div>
                <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">Result</div>
                <div
                  className={cn(
                    'rounded-md border p-3 text-xs leading-5',
                    block.status === 'error'
                      ? 'border-rose-400/20 bg-rose-400/10 text-rose-200'
                      : 'border-slate-800 bg-slate-900/70 text-slate-300',
                  )}
                >
                  {block.error_code && <div className="mb-1 font-medium text-rose-300">{block.error_code}</div>}
                  {block.output_preview && <pre className="whitespace-pre-wrap break-words">{block.output_preview}</pre>}
                  {block.output_truncated && <div className="mt-2 text-slate-500">输出已截断，可在 Workspace 中查看产物。</div>}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
