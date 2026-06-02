import {
  AlertTriangle,
  CheckCircle2,
  Check,
  Copy,
  Download,
  ExternalLink,
  Clock3,
  Loader2,
  Package,
  Rocket,
  Square,
  Trash2,
} from 'lucide-react';
import { useState } from 'react';
import * as deploymentsAdapter from '@/lib/adapters/deployments';
import { useDeploymentStatus, useStopDeployment } from '@/hooks/useDeployments';
import { handleExternalLink } from '@/lib/nativeShell';
import type { DeploymentStatusBlock as DeploymentStatusBlockType } from '@/lib/types';
import { cn } from '@/lib/utils';

const STATUS_META = {
  queued: {
    label: 'Queued',
    icon: Clock3,
    className: 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-400/25 dark:bg-sky-400/10 dark:text-sky-200',
  },
  publishing: {
    label: 'Publishing',
    icon: Rocket,
    className: 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200',
  },
  published: {
    label: 'Published',
    icon: CheckCircle2,
    className: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/25 dark:bg-emerald-400/10 dark:text-emerald-300',
  },
  failed: {
    label: 'Failed',
    icon: AlertTriangle,
    className: 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-400/25 dark:bg-rose-400/10 dark:text-rose-300',
  },
  stopped: {
    label: 'Stopped',
    icon: Square,
    className: 'border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
  },
  not_supported: {
    label: 'Not supported',
    icon: AlertTriangle,
    className: 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-400/25 dark:bg-sky-400/10 dark:text-sky-200',
  },
} as const;

const KIND_LABELS = {
  static_site: 'Static site',
  source_zip: 'Source archive',
  container: 'Container',
} as const;

function formatBytes(size?: number): string | null {
  if (!size) return null;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function filenameFor(block: DeploymentStatusBlockType): string {
  if (block.kind === 'source_zip') return `agenthub-source-${block.deployment_id}.zip`;
  return `agenthub-deployment-${block.deployment_id}.zip`;
}

export function DeploymentStatusBlock({
  block,
  conversationId,
}: {
  block: DeploymentStatusBlockType;
  conversationId?: string;
}) {
  const statusQuery = useDeploymentStatus(conversationId, block.deployment_id);
  const stopDeployment = useStopDeployment(conversationId);
  const deployment = statusQuery.data;
  const status = deployment?.status ?? block.status;
  const kind = deployment?.kind ?? block.kind;
  const url = deployment?.url ?? block.url;
  const downloadUrl = deployment?.download_url ?? block.download_url;
  const error = deployment?.error ?? block.error;
  const logsPreview = deployment?.logs.join('\n') || block.logs_preview;
  const meta = STATUS_META[status];
  const StatusIcon = meta.icon;
  const [downloadState, setDownloadState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle');
  const sizeLabel = formatBytes(deployment?.size_bytes ?? block.size_bytes);
  const canStop = Boolean(conversationId) && ['publishing', 'published'].includes(status);

  async function downloadSource() {
    if (!conversationId || !downloadUrl || downloadState === 'loading') return;
    setDownloadState('loading');
    try {
      const archive = await deploymentsAdapter.downloadSourceArchive(
        conversationId,
        block.deployment_id,
        downloadUrl,
      );
      const href = URL.createObjectURL(archive);
      const anchor = document.createElement('a');
      anchor.href = href;
      anchor.download = filenameFor(block);
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(href);
      setDownloadState('idle');
    } catch {
      setDownloadState('error');
    }
  }

  async function copyUrl() {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopyState('copied');
      window.setTimeout(() => setCopyState('idle'), 1_500);
    } catch {
      setCopyState('error');
    }
  }

  function stop() {
    if (!canStop) return;
    stopDeployment.mutate(block.deployment_id);
  }

  return (
    <section className="overflow-hidden rounded-md border border-slate-300 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950/70">
      <div className="flex min-w-0 flex-wrap items-start gap-3 px-3 py-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-slate-300 bg-slate-50 text-brand dark:border-slate-800 dark:bg-slate-900 dark:text-brand-light">
          <Package className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-slate-950 dark:text-white">
              {block.title || KIND_LABELS[block.kind]}
            </h3>
            <span className={cn('inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-xs', meta.className)}>
              <StatusIcon className="h-3.5 w-3.5" />
              {meta.label}
            </span>
          </div>
          <div className="mt-1 truncate text-xs text-slate-500">
            {KIND_LABELS[kind]} · {block.deployment_id}
            {sizeLabel ? ` · ${sizeLabel}` : ''}
          </div>
          {status === 'publishing' && (
            <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-200">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              正在刷新发布状态...
            </p>
          )}
          {kind === 'source_zip' && status === 'published' && (
            <p className="mt-2 text-xs text-slate-500">源码包为临时产物，请及时下载并妥善保存。</p>
          )}
          {error && (
            <p className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-800 dark:border-rose-400/25 dark:bg-rose-950/25 dark:text-rose-100">
              {error}
            </p>
          )}
          {logsPreview && (
            <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600 scrollbar-thin dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
              {logsPreview}
            </pre>
          )}
          {downloadState === 'error' && (
            <p className="mt-2 text-xs text-rose-600 dark:text-rose-300">源码下载失败，请稍后重试。</p>
          )}
          {copyState === 'error' && (
            <p className="mt-2 text-xs text-rose-600 dark:text-rose-300">复制失败，请手动复制部署地址。</p>
          )}
          {stopDeployment.isError && (
            <p className="mt-2 text-xs text-rose-600 dark:text-rose-300">停止发布失败，请稍后重试。</p>
          )}
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          {url && (
            <a
              href={url}
              onClick={(event) => handleExternalLink(event, url)}
              target="_blank"
              rel="noreferrer"
              className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
              title="打开部署地址"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          )}
          {url && (
            <button
              type="button"
              onClick={() => void copyUrl()}
              className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
              title={copyState === 'copied' ? '已复制部署地址' : '复制部署地址'}
              aria-label={copyState === 'copied' ? '已复制部署地址' : '复制部署地址'}
            >
              {copyState === 'copied' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </button>
          )}
          {downloadUrl && conversationId && (
            <button
              type="button"
              onClick={() => void downloadSource()}
              className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-950 disabled:cursor-wait disabled:opacity-60 dark:hover:bg-slate-800 dark:hover:text-white"
              title="下载源码"
              aria-label="下载源码"
              disabled={downloadState === 'loading'}
            >
              {downloadState === 'loading' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            </button>
          )}
          {canStop && (
            <button
              type="button"
              onClick={stop}
              className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-rose-50 hover:text-rose-700 disabled:cursor-wait disabled:opacity-60 dark:hover:bg-rose-400/10 dark:hover:text-rose-300"
              title={kind === 'source_zip' ? '删除源码包' : '停止发布'}
              aria-label={kind === 'source_zip' ? '删除源码包' : '停止发布'}
              disabled={stopDeployment.isPending}
            >
              {stopDeployment.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : kind === 'source_zip' ? <Trash2 className="h-4 w-4" /> : <Square className="h-4 w-4" />}
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
