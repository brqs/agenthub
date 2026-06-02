import { Check, Copy, ExternalLink, History, Loader2, Square, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useDeployments, useStopDeployment } from '@/hooks/useDeployments';
import type { WorkspaceDeploymentResponse } from '@/lib/types';
import { handleExternalLink } from '@/lib/nativeShell';

const STATUS_LABELS: Record<WorkspaceDeploymentResponse['status'], string> = {
  queued: 'Queued',
  publishing: 'Publishing',
  published: 'Published',
  failed: 'Failed',
  stopped: 'Stopped',
  not_supported: 'Not supported',
};

const KIND_LABELS: Record<WorkspaceDeploymentResponse['kind'], string> = {
  static_site: 'Static site',
  source_zip: 'Source archive',
  container: 'Container',
};

export function DeploymentHistory({ conversationId }: { conversationId: string }) {
  const deploymentsQuery = useDeployments(conversationId);
  const stopDeployment = useStopDeployment(conversationId);
  const [copiedDeploymentId, setCopiedDeploymentId] = useState<string | null>(null);
  const [copyError, setCopyError] = useState(false);
  const deployments = deploymentsQuery.data?.items ?? [];

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
        {deploymentsQuery.isFetching && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-500" />}
      </div>

      {deploymentsQuery.isLoading ? (
        <div className="rounded-md border border-slate-300 p-3 text-xs text-slate-500 dark:border-slate-800">
          正在加载发布记录...
        </div>
      ) : deploymentsQuery.isError ? (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-3 text-xs text-rose-700 dark:border-rose-400/25 dark:bg-rose-950/20 dark:text-rose-200">
          发布记录加载失败，请稍后重试。
        </div>
      ) : deployments.length ? (
        <div className="space-y-2">
          {deployments.map((deployment) => (
            <DeploymentHistoryItem
              key={deployment.id}
              deployment={deployment}
              copied={copiedDeploymentId === deployment.id}
              stopping={stopDeployment.isPending && stopDeployment.variables === deployment.id}
              onCopy={() => void copyUrl(deployment)}
              onStop={() => stopDeployment.mutate(deployment.id)}
            />
          ))}
          {copyError && (
            <p className="text-xs text-rose-600 dark:text-rose-300">复制失败，请手动复制部署地址。</p>
          )}
          {stopDeployment.isError && (
            <p className="text-xs text-rose-600 dark:text-rose-300">停止发布失败，请稍后重试。</p>
          )}
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-slate-300 p-3 text-xs leading-5 text-slate-500 dark:border-slate-800">
          暂无发布记录。向 Orchestrator 发送部署指令后，状态会显示在这里。
        </div>
      )}
    </section>
  );
}

function DeploymentHistoryItem({
  deployment,
  copied,
  stopping,
  onCopy,
  onStop,
}: {
  deployment: WorkspaceDeploymentResponse;
  copied: boolean;
  stopping: boolean;
  onCopy: () => void;
  onStop: () => void;
}) {
  const canStop = ['publishing', 'published'].includes(deployment.status);

  return (
    <div className="rounded-md border border-slate-300 bg-white p-3 dark:border-slate-800 dark:bg-slate-950/60">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-medium text-slate-900 dark:text-slate-200">
            {KIND_LABELS[deployment.kind]}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
            <span>{STATUS_LABELS[deployment.status]}</span>
            <span>·</span>
            <span>{new Date(deployment.updated_at).toLocaleString()}</span>
          </div>
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
              {stopping ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : deployment.kind === 'source_zip' ? <Trash2 className="h-3.5 w-3.5" /> : <Square className="h-3.5 w-3.5" />}
            </button>
          )}
        </div>
      </div>
      {deployment.kind === 'source_zip' && deployment.status === 'published' && (
        <p className="mt-2 text-[11px] leading-5 text-slate-500">临时源码包，请及时下载并妥善保存。</p>
      )}
    </div>
  );
}
