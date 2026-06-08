import {
  Check,
  Copy,
  Download,
  ExternalLink,
  History,
  Loader2,
  RotateCcw,
  Square,
  Trash2,
} from 'lucide-react';
import { useState } from 'react';
import {
  DEPLOYMENT_KIND_LABELS,
  DEPLOYMENT_STATUS_META,
  formatBytes,
  formatDateTime,
  isDeploymentInProgress,
} from './deploymentPresentation';
import { useDeployments, useRetryDeployment, useStopDeployment } from '@/hooks/useDeployments';
import * as deploymentsAdapter from '@/lib/adapters/deployments';
import type { WorkspaceDeploymentResponse } from '@/lib/types';
import { handleExternalLink } from '@/lib/nativeShell';

export function DeploymentHistory({ conversationId }: { conversationId: string }) {
  const deploymentsQuery = useDeployments(conversationId);
  const stopDeployment = useStopDeployment(conversationId);
  const retryDeployment = useRetryDeployment(conversationId);
  const [copiedDeploymentId, setCopiedDeploymentId] = useState<string | null>(null);
  const [copyError, setCopyError] = useState(false);
  const deployments = deploymentsQuery.data?.items ?? [];
  const hasDeploymentData = Boolean(deploymentsQuery.data);
  const showPrimaryError = deploymentsQuery.isError && !hasDeploymentData;
  const showRefreshWarning = deploymentsQuery.isError && hasDeploymentData;

  async function copyUrl(deployment: WorkspaceDeploymentResponse) {
    if (!deployment.url) return;
    try {
      await navigator.clipboard.writeText(deployment.url);
      setCopyError(false);
      setCopiedDeploymentId(deployment.id);
      window.setTimeout(() => setCopiedDeploymentId(null), 1_500);
    } catch {
      setCopyError(true);
    }
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <History className="h-3.5 w-3.5" />
          <span>发布历史</span>
        </div>
        {deploymentsQuery.isFetching && (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-500" />
        )}
      </div>

      {deploymentsQuery.isLoading ? (
        <div className="rounded-md border border-slate-300 p-3 text-xs text-slate-500 dark:border-slate-800">
          正在加载发布记录...
        </div>
      ) : showPrimaryError ? (
        <div className="space-y-2 rounded-md border border-rose-300 bg-rose-50 p-3 text-xs text-rose-700 dark:border-rose-400/25 dark:bg-rose-950/20 dark:text-rose-200">
          发布记录加载失败，请稍后重试。
          <button
            type="button"
            onClick={() => void deploymentsQuery.refetch()}
            className="inline-flex items-center gap-1 rounded-md border border-rose-300 bg-white px-2 py-1 font-medium text-rose-700 hover:bg-rose-100 dark:border-rose-400/30 dark:bg-rose-950/40 dark:text-rose-100 dark:hover:bg-rose-900/40"
            aria-label="重试加载发布记录"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            重试
          </button>
        </div>
      ) : deployments.length ? (
        <div className="space-y-2">
          {showRefreshWarning && <DeploymentRefreshWarning onRetry={deploymentsQuery.refetch} />}
          {deployments.map((deployment) => (
            <DeploymentHistoryItem
              key={deployment.id}
              conversationId={conversationId}
              deployment={deployment}
              copied={copiedDeploymentId === deployment.id}
              stopping={stopDeployment.isPending && stopDeployment.variables === deployment.id}
              retrying={retryDeployment.isPending && retryDeployment.variables === deployment.id}
              onCopy={() => void copyUrl(deployment)}
              onStop={() => stopDeployment.mutate(deployment.id)}
              onRetry={() => retryDeployment.mutate(deployment.id)}
            />
          ))}
          {copyError && (
            <p className="text-xs text-rose-600 dark:text-rose-300">
              复制失败，请手动复制部署地址。
            </p>
          )}
          {stopDeployment.isError && (
            <p className="text-xs text-rose-600 dark:text-rose-300">停止发布失败，请稍后重试。</p>
          )}
          {retryDeployment.isError && (
            <p className="text-xs text-rose-600 dark:text-rose-300">重新发布失败，请稍后重试。</p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {showRefreshWarning && <DeploymentRefreshWarning onRetry={deploymentsQuery.refetch} />}
          <div className="rounded-md border border-dashed border-slate-300 p-3 text-xs leading-5 text-slate-500 dark:border-slate-800">
          暂无发布记录。向 Orchestrator 发送部署指令后，状态会显示在这里。
          </div>
        </div>
      )}
    </section>
  );
}

function DeploymentRefreshWarning({ onRetry }: { onRetry: () => unknown }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-400/30 dark:bg-amber-950/20 dark:text-amber-100">
      <span>Deployment history could not refresh; showing the last known state.</span>
      <button
        type="button"
        onClick={() => void onRetry()}
        className="inline-flex shrink-0 items-center gap-1 rounded border border-amber-300 bg-white px-2 py-1 font-medium hover:bg-amber-100 dark:border-amber-400/30 dark:bg-amber-950/40 dark:hover:bg-amber-900/40"
        aria-label="重试刷新发布记录"
      >
        <RotateCcw className="h-3.5 w-3.5" />
        重试
      </button>
    </div>
  );
}

function DeploymentHistoryItem({
  conversationId,
  deployment,
  copied,
  stopping,
  retrying,
  onCopy,
  onStop,
  onRetry,
}: {
  conversationId: string;
  deployment: WorkspaceDeploymentResponse;
  copied: boolean;
  stopping: boolean;
  retrying: boolean;
  onCopy: () => void;
  onStop: () => void;
  onRetry: () => void;
}) {
  const canStop = ['queued', 'publishing', 'published'].includes(deployment.status);
  const canRetry = ['failed', 'stopped', 'not_supported'].includes(deployment.status);
  const canDownloadSource = deployment.kind === 'source_zip' && deployment.status === 'published';
  const statusMeta = DEPLOYMENT_STATUS_META[deployment.status];
  const updatedAt = formatDateTime(deployment.updated_at);
  const sizeLabel = formatBytes(deployment.size_bytes);
  const [downloadState, setDownloadState] = useState<'idle' | 'loading' | 'error'>('idle');

  async function downloadSource() {
    if (!canDownloadSource || downloadState === 'loading') return;
    setDownloadState('loading');
    try {
      const archive = await deploymentsAdapter.downloadSourceArchive(
        conversationId,
        deployment.id,
        deployment.download_url,
      );
      const href = URL.createObjectURL(archive);
      const anchor = document.createElement('a');
      anchor.href = href;
      anchor.download = `agenthub-source-${deployment.id}.zip`;
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
    <div className="rounded-md border border-slate-300 bg-white p-3 dark:border-slate-800 dark:bg-slate-950/60">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-medium text-slate-900 dark:text-slate-200">
            {DEPLOYMENT_KIND_LABELS[deployment.kind]}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
            <span className="font-medium text-slate-600 dark:text-slate-400">
              {statusMeta.label}
            </span>
            {updatedAt && (
              <>
                <span>·</span>
                <span>{updatedAt}</span>
              </>
            )}
            {sizeLabel && (
              <>
                <span>·</span>
                <span>{sizeLabel}</span>
              </>
            )}
          </div>
          {deployment.error && (
            <p className="mt-2 line-clamp-2 text-[11px] leading-5 text-rose-600 dark:text-rose-300">
              {deployment.error}
            </p>
          )}
          {deployment.kind === 'container' &&
            (deployment.runtime_status || deployment.host_port) && (
              <p className="mt-2 truncate text-[11px] leading-5 text-slate-500">
                {deployment.runtime_status
                  ? `运行状态：${deployment.runtime_status}`
                  : '容器运行中'}
                {deployment.host_port ? ` · 端口 ${deployment.host_port}` : ''}
              </p>
            )}
          {canDownloadSource && (
            <button
              type="button"
              onClick={() => void downloadSource()}
              disabled={downloadState === 'loading'}
              className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-2.5 py-1.5 text-[11px] font-medium text-slate-700 transition hover:border-brand/40 hover:bg-slate-50 hover:text-slate-950 disabled:cursor-wait disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800 dark:hover:text-white"
              title="下载源码包"
              aria-label="下载源码包"
            >
              {downloadState === 'loading' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              下载源码包
            </button>
          )}
          {downloadState === 'error' && (
            <p className="mt-2 text-[11px] leading-5 text-rose-600 dark:text-rose-300">
              源码下载失败，请稍后重试。
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          {deployment.url && (
            <>
              <a
                href={deployment.url}
                onClick={(event) => handleExternalLink(event, deployment.url)}
                target="_blank"
                rel="noreferrer"
                className="rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
                title="打开部署地址"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
              <button
                type="button"
                onClick={onCopy}
                className="rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
                title={copied ? '已复制部署地址' : '复制部署地址'}
                aria-label={copied ? '已复制部署地址' : '复制部署地址'}
              >
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </>
          )}
          {canStop && (
            <button
              type="button"
              onClick={onStop}
              disabled={stopping}
              className="rounded p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-700 disabled:cursor-wait disabled:opacity-60 dark:hover:bg-rose-400/10 dark:hover:text-rose-300"
              title={deployment.kind === 'source_zip' ? '删除源码包' : '停止发布'}
              aria-label={deployment.kind === 'source_zip' ? '删除源码包' : '停止发布'}
            >
              {stopping ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : deployment.kind === 'source_zip' ? (
                <Trash2 className="h-3.5 w-3.5" />
              ) : (
                <Square className="h-3.5 w-3.5" />
              )}
            </button>
          )}
          {canRetry && (
            <button
              type="button"
              onClick={onRetry}
              disabled={retrying}
              className="rounded p-1.5 text-slate-500 hover:bg-sky-50 hover:text-sky-700 disabled:cursor-wait disabled:opacity-60 dark:hover:bg-sky-400/10 dark:hover:text-sky-200"
              title="重新发布"
              aria-label="重新发布"
            >
              {retrying ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RotateCcw className="h-3.5 w-3.5" />
              )}
            </button>
          )}
        </div>
      </div>
      {isDeploymentInProgress(deployment.status) && (
        <p className="mt-2 inline-flex items-center gap-1.5 text-[11px] leading-5 text-amber-700 dark:text-amber-200">
          <Loader2 className="h-3 w-3 animate-spin" />
          平台正在处理，发布历史会自动刷新。
        </p>
      )}
      {deployment.kind === 'source_zip' && deployment.status === 'published' && (
        <p className="mt-2 text-[11px] leading-5 text-slate-500">
          临时源码包，请及时下载并妥善保存。
        </p>
      )}
    </div>
  );
}
