import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Clock3, Terminal } from 'lucide-react';
import { useState } from 'react';
import { SyntaxHighlightedCode } from './SyntaxHighlightedCode';
import type { ToolCallBlock as ToolCallBlockType } from '@/lib/types';
import { cn } from '@/lib/utils';

const STATUS_META = {
  pending: {
    label: 'Running',
    className: 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-200',
    icon: Clock3,
  },
  ok: {
    label: 'Done',
    className: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300',
    icon: CheckCircle2,
  },
  error: {
    label: 'Error',
    className: 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-400/20 dark:bg-rose-400/10 dark:text-rose-300',
    icon: AlertTriangle,
  },
} as const;

function formatJson(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2);
}

function getResultLanguage(block: ToolCallBlockType): string {
  if (!block.output_preview) return 'text';
  if (block.tool_name.toLowerCase().includes('bash')) return 'bash';
  const trimmedOutput = block.output_preview.trim();
  if (
    (trimmedOutput.startsWith('{') && trimmedOutput.endsWith('}')) ||
    (trimmedOutput.startsWith('[') && trimmedOutput.endsWith(']'))
  ) {
    return 'json';
  }
  return 'text';
}

export function ToolCallBlock({ block }: { block: ToolCallBlockType }) {
  const [open, setOpen] = useState(block.status !== 'ok');
  const meta = STATUS_META[block.status];
  const StatusIcon = meta.icon;
  const ToggleIcon = open ? ChevronDown : ChevronRight;
  const hasError = block.status === 'error';

  return (
    <section
      className={cn(
        'mobile-text-safe overflow-hidden rounded-md border bg-white shadow-sm dark:bg-slate-950/70',
        hasError
          ? 'border-rose-200 ring-1 ring-rose-100 dark:border-rose-400/30 dark:ring-rose-400/10'
          : 'border-slate-300 dark:border-slate-800',
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full min-w-0 items-center gap-3 px-3 py-2.5 text-left transition hover:bg-slate-50 dark:hover:bg-slate-900/70"
      >
        <ToggleIcon className="h-4 w-4 shrink-0 text-slate-500" />
        <span
          className={cn(
            'flex h-7 w-7 shrink-0 items-center justify-center rounded-md border bg-white dark:bg-slate-900',
            hasError
              ? 'border-rose-200 text-rose-600 dark:border-rose-400/30 dark:text-rose-300'
              : 'border-slate-300 text-brand dark:border-slate-800 dark:text-brand-light',
          )}
        >
          <Terminal className="h-4 w-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="mobile-text-safe block text-sm font-semibold text-slate-950 dark:text-white sm:truncate">{block.tool_name}</span>
          <span className="mobile-text-safe block text-xs text-slate-500 sm:truncate">{block.call_id}</span>
        </span>
        <span className={cn('inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-xs', meta.className)}>
          <StatusIcon className="h-3.5 w-3.5" />
          {meta.label}
        </span>
      </button>

      {open && (
        <div className="mobile-text-safe border-t border-slate-200 px-3 py-3 dark:border-slate-800">
          <div className="grid gap-3">
            <div>
              <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400">Arguments</div>
                <div className="max-h-44 max-w-full overflow-auto rounded-md border border-slate-300 bg-slate-50 p-3 text-xs leading-5 scrollbar-thin dark:border-slate-800 dark:bg-slate-950">
                <SyntaxHighlightedCode
                  code={formatJson(block.arguments)}
                  language="json"
                  className="text-xs leading-5"
                  fallbackClassName="text-xs leading-5"
                />
              </div>
            </div>

            {(block.output_preview || block.error_code) && (
              <div>
                <div
                  className={cn(
                    'mb-1.5 text-xs font-semibold uppercase tracking-wide',
                    hasError ? 'text-rose-700 dark:text-rose-300' : 'text-slate-600 dark:text-slate-400',
                  )}
                >
                  Result
                </div>
                <div
                  className={cn(
                    'mobile-text-safe rounded-md border p-3 text-xs leading-5',
                    hasError
                      ? 'border-rose-200 bg-rose-50 text-rose-900 shadow-sm shadow-rose-100/70 dark:border-rose-400/25 dark:bg-rose-950/25 dark:text-rose-100 dark:shadow-none'
                      : 'border-slate-300 bg-white text-slate-800 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-300',
                  )}
                >
                  {block.error_code && (
                    <div className="mb-1 border-l-2 border-rose-500 pl-2 font-semibold text-rose-700 dark:text-rose-300">
                      {block.error_code}
                    </div>
                  )}
                  {block.output_preview && (
                    <SyntaxHighlightedCode
                      code={block.output_preview}
                      language={getResultLanguage(block)}
                      className="max-h-52 text-xs leading-5 [&_code]:whitespace-pre-wrap [&_pre]:!min-w-0"
                      fallbackClassName="max-h-52 whitespace-pre-wrap break-words text-xs leading-5"
                    />
                  )}
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
