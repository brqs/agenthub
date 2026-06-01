import {
  AlertTriangle,
  CheckCircle2,
  Download,
  ExternalLink,
  Package,
  Rocket,
  Square,
} from 'lucide-react';
import { useState } from 'react';
import { api } from '@/lib/api';
import type { DeploymentStatusBlock as DeploymentStatusBlockType } from '@/lib/types';
import { cn } from '@/lib/utils';

const STATUS_META = {
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

export function DeploymentStatusBlock({ block }: { block: DeploymentStatusBlockType }) {
  const meta = STATUS_META[block.status];
  const StatusIcon = meta.icon;
  const [downloadState, setDownloadState] = useState<'idle' | 'loading' | 'error'>('idle');
  const sizeLabel = formatBytes(block.size_bytes);

  async function downloadSource() {
    if (!block.download_url || downloadState === 'loading') return;
    setDownloadState('loading');
    try {
      const response = await api.get<Blob>(block.download_url, { responseType: 'blob' });
      const href = URL.createObjectURL(response.data);
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

  return (
    <section className="overflow-hidden rounded-md border border-slate-300 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950/70">
      <div className="flex min-w-0 items-start gap-3 px-3 py-3">
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
            {KIND_LABELS[block.kind]} · {block.deployment_id}
            {sizeLabel ? ` · ${sizeLabel}` : ''}
          </div>
          {block.error && (
            <p className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-800 dark:border-rose-400/25 dark:bg-rose-950/25 dark:text-rose-100">
              {block.error}
            </p>
          )}
          {block.logs_preview && (
            <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600 scrollbar-thin dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
              {block.logs_preview}
            </pre>
          )}
          {downloadState === 'error' && (
            <p className="mt-2 text-xs text-rose-600 dark:text-rose-300">源码下载失败，请稍后重试。</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {block.url && (
            <a
              href={block.url}
              target="_blank"
              rel="noreferrer"
              className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
              title="打开部署地址"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          )}
          {block.download_url && (
            <button
              type="button"
              onClick={downloadSource}
              className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-950 disabled:cursor-wait disabled:opacity-60 dark:hover:bg-slate-800 dark:hover:text-white"
              title="下载源码"
              disabled={downloadState === 'loading'}
            >
              <Download className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
