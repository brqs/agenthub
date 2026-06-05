import { CheckCircle2, Code2, RotateCcw, SearchCheck, XCircle } from 'lucide-react';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import { buildReviewThreadItems, type ReviewThreadItem } from './reviewThreadModel';
import type { Agent, OrchestratorRunDetail } from '@/lib/types';

export function ReviewThreadTimeline({
  detail,
  agents,
}: {
  detail: OrchestratorRunDetail | null | undefined;
  agents: Agent[];
}) {
  const items = buildReviewThreadItems(detail);
  if (items.length === 0) return null;

  return (
    <section className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950/70">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Review / Handoff Timeline
        </div>
        <div className="text-[11px] text-slate-500">{items.length} nodes</div>
      </div>
      <div className="space-y-3">
        {items.map((item) => (
          <TimelineNode key={item.taskId} item={item} agents={agents} />
        ))}
      </div>
    </section>
  );
}

function TimelineNode({ item, agents }: { item: ReviewThreadItem; agents: Agent[] }) {
  const agent = agents.find((candidate) => candidate.id === item.agentId);
  const Icon = item.kind === 'implementation' ? Code2 : item.kind === 'review' ? SearchCheck : RotateCcw;
  const state = item.kind === 'review' ? item.outcome : item.state;
  const badge = stateBadge(state);
  const BadgeIcon = badge.icon;

  return (
    <div className="flex gap-3 rounded-md border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900/75">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-brand/10 text-brand dark:text-brand-light">
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold uppercase text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {kindLabel(item.kind)}
          </span>
          <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${badge.className}`}>
            <BadgeIcon className="h-3 w-3" />
            {badge.label}
          </span>
        </div>
        <div className="mt-2 flex min-w-0 items-center gap-2">
          <AgentAvatar agent={agent} size="sm" />
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
              {item.title}
            </div>
            <div className="truncate text-xs text-slate-500">
              @{agent?.name ?? item.agentId} · {item.taskId}
            </div>
          </div>
        </div>
        <TimelineMetadata item={item} />
      </div>
    </div>
  );
}

function TimelineMetadata({ item }: { item: ReviewThreadItem }) {
  const chips: string[] = [];
  const errorSummary = failureSummary(item);
  const summary = timelineSummary(item);
  if (item.kind === 'implementation') {
    chips.push(...item.artifactPaths.slice(0, 3));
  }
  if (item.kind === 'review' && item.reviewOf.length > 0) {
    chips.push(`review of ${item.reviewOf.join(', ')}`);
  }
  if (item.kind === 'repair') {
    if (item.reviewOf.length > 0) chips.push(`repair from ${item.reviewOf.join(', ')}`);
    if (item.handoffReason) chips.push(item.handoffReason);
  }

  return (
    <>
      {chips.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {chips.map((chip) => (
            <span
              key={chip}
              className="max-w-full truncate rounded border border-slate-200 px-2 py-0.5 text-[11px] text-slate-500 dark:border-slate-800"
            >
              {chip}
            </span>
          ))}
        </div>
      )}
      {errorSummary && (
        <p className="mt-2 line-clamp-2 rounded-md border border-red-200 bg-red-50 px-2 py-1.5 text-xs leading-5 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200">
          {errorSummary}
        </p>
      )}
      {summary && (
        <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-600 dark:text-slate-400">
          {summary}
        </p>
      )}
    </>
  );
}

function timelineSummary(item: ReviewThreadItem): string {
  if (!item.summary || isFailureState(item.state)) return '';
  if (item.kind === 'implementation') return '';
  return item.summary;
}

function failureSummary(item: ReviewThreadItem): string {
  if (!isFailureState(item.state)) return '';
  const text = item.error || item.summary;
  return truncateOneLine(text, 220);
}

function isFailureState(state: string | null | undefined): boolean {
  return state === 'failed' || state === 'error';
}

function truncateOneLine(value: string | null | undefined, maxLength: number): string {
  const text = (value ?? '').replace(/\s+/g, ' ').trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 3)}...`;
}

function kindLabel(kind: ReviewThreadItem['kind']) {
  if (kind === 'implementation') return 'Implementation';
  if (kind === 'review') return 'Review';
  return 'Repair';
}

function stateBadge(state: string | null | undefined) {
  if (state === 'passed' || state === 'succeeded' || state === 'done') {
    return {
      icon: CheckCircle2,
      label: state === 'passed' ? '通过' : '完成',
      className:
        'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200',
    };
  }
  if (state === 'needs_repair') {
    return {
      icon: RotateCcw,
      label: '需要修复',
      className:
        'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200',
    };
  }
  if (state === 'failed' || state === 'error') {
    return {
      icon: XCircle,
      label: '失败',
      className:
        'border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200',
    };
  }
  return {
    icon: SearchCheck,
    label: '未知',
    className:
      'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400',
  };
}
