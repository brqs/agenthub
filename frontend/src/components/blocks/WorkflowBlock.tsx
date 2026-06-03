import { AlertTriangle, CheckCircle2, Circle, PlayCircle, Workflow } from 'lucide-react';
import { SyntaxHighlightedCode } from './SyntaxHighlightedCode';
import type { WorkflowBlock as WorkflowBlockType } from '@/lib/types';
import { cn } from '@/lib/utils';

const STATUS_META = {
  passed: {
    label: 'Passed',
    className:
      'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300',
    icon: CheckCircle2,
  },
  failed: {
    label: 'Failed',
    className:
      'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-400/20 dark:bg-rose-400/10 dark:text-rose-300',
    icon: AlertTriangle,
  },
  unknown: {
    label: 'Unknown',
    className:
      'border-slate-300 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
    icon: Circle,
  },
} as const;

const RUNTIME_LABEL = {
  ready: 'Ready',
  invalid: 'Invalid',
  not_supported: 'Runtime N/A',
} as const;

const DRY_RUN_LABEL = {
  passed: 'Dry run passed',
  failed: 'Dry run failed',
  not_supported: 'Dry run N/A',
} as const;

function asRecords(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    : [];
}

function workflowNodes(block: WorkflowBlockType): Array<Record<string, unknown>> {
  if (block.nodes?.length) return block.nodes;
  return asRecords(block.definition?.nodes);
}

function workflowEdges(block: WorkflowBlockType): Array<Record<string, unknown>> {
  if (block.edges?.length) return block.edges;
  return asRecords(block.definition?.edges);
}

function nodeLabel(node: Record<string, unknown>): string {
  const id = typeof node.id === 'string' && node.id ? node.id : 'node';
  const type = typeof node.type === 'string' && node.type ? node.type : 'step';
  return `${id} · ${type}`;
}

function edgeLabel(edge: Record<string, unknown>): string {
  const source = typeof edge.source === 'string' && edge.source ? edge.source : '?';
  const target = typeof edge.target === 'string' && edge.target ? edge.target : '?';
  return `${source} -> ${target}`;
}

export function WorkflowBlock({ block }: { block: WorkflowBlockType }) {
  const validation = block.validation_status ?? 'unknown';
  const status = STATUS_META[validation];
  const StatusIcon = status.icon;
  const nodes = workflowNodes(block);
  const edges = workflowEdges(block);
  const rawDefinition =
    block.raw_definition ??
    (block.definition && Object.keys(block.definition).length > 0
      ? JSON.stringify(block.definition, null, 2)
      : '');

  return (
    <section className="my-3 overflow-hidden rounded-md border border-slate-300 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950/80">
      <div className="flex min-w-0 items-center gap-3 border-b border-slate-200 px-3 py-2.5 dark:border-slate-800">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-brand/30 bg-brand/10 text-brand dark:text-brand-light">
          <Workflow className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-slate-950 dark:text-white">
            {block.name || 'Workflow'}
          </div>
          <div className="truncate text-xs text-slate-500">
            {[block.path, `${nodes.length} nodes`, `${edges.length} edges`]
              .filter(Boolean)
              .join(' · ')}
          </div>
        </div>
        <span
          className={cn(
            'inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-xs',
            status.className,
          )}
        >
          <StatusIcon className="h-3.5 w-3.5" />
          {status.label}
        </span>
      </div>

      <div className="grid gap-3 p-3">
        <div className="grid gap-2 sm:grid-cols-3">
          <StatusChip label={RUNTIME_LABEL[block.runtime_status ?? 'not_supported']} />
          <StatusChip label={DRY_RUN_LABEL[block.dry_run_status ?? 'not_supported']} />
          <StatusChip label={`Health ${block.health_status ?? 'unknown'}`} />
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="min-w-0">
            <div className="mb-1.5 text-xs font-semibold uppercase text-slate-600 dark:text-slate-400">
              Nodes
            </div>
            <div className="space-y-1">
              {nodes.slice(0, 8).map((node, index) => (
                <div
                  key={`${String(node.id ?? index)}-${index}`}
                  className="truncate rounded border border-slate-200 px-2 py-1.5 text-xs text-slate-700 dark:border-slate-800 dark:text-slate-300"
                >
                  {nodeLabel(node)}
                </div>
              ))}
              {nodes.length === 0 && <div className="text-xs text-slate-500">No nodes</div>}
            </div>
          </div>
          <div className="min-w-0">
            <div className="mb-1.5 text-xs font-semibold uppercase text-slate-600 dark:text-slate-400">
              Edges
            </div>
            <div className="space-y-1">
              {edges.slice(0, 8).map((edge, index) => (
                <div
                  key={`${edgeLabel(edge)}-${index}`}
                  className="truncate rounded border border-slate-200 px-2 py-1.5 text-xs text-slate-700 dark:border-slate-800 dark:text-slate-300"
                >
                  {edgeLabel(edge)}
                </div>
              ))}
              {edges.length === 0 && <div className="text-xs text-slate-500">No edges</div>}
            </div>
          </div>
        </div>

        {block.validation_errors && block.validation_errors.length > 0 && (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-2 text-xs text-rose-800 dark:border-rose-400/25 dark:bg-rose-950/25 dark:text-rose-100">
            {block.validation_errors.slice(0, 4).join(', ')}
          </div>
        )}

        {rawDefinition && (
          <div className="max-h-56 overflow-auto rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950">
            <SyntaxHighlightedCode
              code={rawDefinition}
              language={block.format === 'json' ? 'json' : 'yaml'}
              className="text-xs leading-5"
              fallbackClassName="whitespace-pre-wrap break-words text-xs leading-5"
            />
          </div>
        )}
      </div>
    </section>
  );
}

function StatusChip({ label }: { label: string }) {
  return (
    <div className="inline-flex min-w-0 items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-300">
      <PlayCircle className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate">{label}</span>
    </div>
  );
}
