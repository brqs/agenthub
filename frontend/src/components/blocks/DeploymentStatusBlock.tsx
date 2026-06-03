import { Check, Copy, Download, ExternalLink, Loader2, Package, Square, Trash2 } from 'lucide-react';
import { useState } from 'react';
import {
  DEPLOYMENT_KIND_LABELS,
  DEPLOYMENT_STATUS_META,
  buildDeploymentTimeline,
  deploymentTitle,
  formatBytes,
  formatDateTime,
  type DeploymentLike,
} from '@/components/artifact/deploymentPresentation';
import * as deploymentsAdapter from '@/lib/adapters/deployments';
import { useDeploymentStatus, useStopDeployment } from '@/hooks/useDeployments';
import { handleExternalLink } from '@/lib/nativeShell';
import type { DeploymentStatusBlock as DeploymentStatusBlockType } from '@/lib/types';
import { cn } from '@/lib/utils';

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
  const logsPreview = deployment?.logs_tail ?? (deployment?.logs ?? []).join('\n') ?? block.logs_preview;
  const meta = DEPLOYMENT_STATUS_META[status];
  const StatusIcon = meta.icon;
  const [downloadState, setDownloadState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle');
  const sizeLabel = formatBytes(deployment?.size_bytes ?? block.size_bytes);
  const canStop = Boolean(conversationId) && ['publishing', 'published'].includes(status);
  const deploymentLike: DeploymentLike = {
    ...block,
    ...deployment,
    kind,
    status,
    title: block.title,
    created_at: deployment?.created_at,
    updated_at: deployment?.updated_at,
  };

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
              {deploymentTitle(deploymentLike)}
            </h3>
            <span className={cn('inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-xs', meta.className)}>
              <StatusIcon className={cn('h-3.5 w-3.5', status === 'publishing' && 'animate-spin')} />
              {meta.label}
            </span>
          </div>
          <div className="mt-1 truncate text-xs text-slate-500">
            {DEPLOYMENT_KIND_LABELS[kind]} · {block.deployment_id}
            {sizeLabel ? ` · ${sizeLabel}` : ''}
          </div>
          {(status === 'queued' || status === 'publishing') && (
            <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-200">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {status === 'queued' ? '已进入发布队列，等待平台 worker 处理...' : '正在刷新发布状态...'}
            </p>
          )}
          <DeploymentSummary deployment={deploymentLike} />
          <DeploymentTimeline deployment={deploymentLike} />
          {kind === 'source_zip' && status === 'published' && (
            <p className="mt-2 text-xs text-slate-500">源码包为临时产物，请及时下载并妥善保存。</p>
          )}
          {status === 'not_supported' && (
            <p className="mt-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-800 dark:border-sky-400/25 dark:bg-sky-950/25 dark:text-sky-100">
              当前环境暂未开启容器部署 worker。前端会保留记录，你可以继续使用静态发布或源码打包。
            </p>
          )}
          {error && (
            <p className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-800 dark:border-rose-400/25 dark:bg-rose-950/25 dark:text-rose-100">
              {error}
            </p>
          )}
          {logsPreview && (
            <details className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
              <summary className="cursor-pointer font-medium text-slate-700 dark:text-slate-300">
                {kind === 'container' ? '查看容器日志' : '查看发布日志'}
              </summary>
              <pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap leading-5 scrollbar-thin">
                {logsPreview}
              </pre>
            </details>
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

function DeploymentSummary({ deployment }: { deployment: DeploymentLike }) {
  const publishedAt = formatDateTime(deployment.published_at);
  const stoppedAt = formatDateTime(deployment.stopped_at);
  const expiresAt = formatDateTime(deployment.expires_at);
  const fields = [
    deployment.file_count ? ['文件数', `${deployment.file_count}`] : null,
    deployment.artifact_digest ? ['摘要', deployment.artifact_digest.slice(0, 12)] : null,
    publishedAt ? ['发布时间', publishedAt] : null,
    stoppedAt ? ['停止时间', stoppedAt] : null,
    expiresAt ? ['过期时间', expiresAt] : null,
    deployment.host_port ? ['宿主端口', `${deployment.host_port}`] : null,
    deployment.container_port ? ['容器端口', `${deployment.container_port}`] : null,
    deployment.runtime_status ? ['运行状态', deployment.runtime_status] : null,
  ].filter((field): field is [string, string] => Boolean(field));

  if (!fields.length && !deployment.healthcheck_url && !deployment.container_id && !deployment.image_id) {
    return null;
  }

  return (
    <dl className="mt-3 grid gap-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs dark:border-slate-800 dark:bg-slate-950/70 sm:grid-cols-2">
      {fields.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-slate-500">{label}</dt>
          <dd className="mt-0.5 truncate font-medium text-slate-800 dark:text-slate-200" title={value}>
            {value}
          </dd>
        </div>
      ))}
      {deployment.healthcheck_url && (
        <div className="min-w-0 sm:col-span-2">
          <dt className="text-slate-500">健康检查</dt>
          <dd className="mt-0.5 truncate font-medium text-slate-800 dark:text-slate-200" title={deployment.healthcheck_url}>
            {deployment.healthcheck_url}
          </dd>
        </div>
      )}
      {deployment.image_id && (
        <div className="min-w-0">
          <dt className="text-slate-500">镜像 ID</dt>
          <dd className="mt-0.5 truncate font-mono text-slate-800 dark:text-slate-200" title={deployment.image_id}>
            {deployment.image_id}
          </dd>
        </div>
      )}
      {deployment.container_id && (
        <div className="min-w-0">
          <dt className="text-slate-500">容器 ID</dt>
          <dd className="mt-0.5 truncate font-mono text-slate-800 dark:text-slate-200" title={deployment.container_id}>
            {deployment.container_id}
          </dd>
        </div>
      )}
    </dl>
  );
}

function DeploymentTimeline({ deployment }: { deployment: DeploymentLike }) {
  const timeline = buildDeploymentTimeline(deployment);
  if (timeline.length <= 1) return null;

  return (
    <ol className="mt-3 space-y-2 rounded-md border border-slate-200 bg-white p-3 text-xs dark:border-slate-800 dark:bg-slate-950/50">
      {timeline.map((step) => (
        <li key={step.key} className="flex gap-2">
          <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-brand dark:bg-brand-light" />
          <span className="min-w-0">
            <span className="block text-slate-800 dark:text-slate-200">{step.label}</span>
            {formatDateTime(step.time) && (
              <span className="mt-0.5 block text-slate-500">{formatDateTime(step.time)}</span>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}
