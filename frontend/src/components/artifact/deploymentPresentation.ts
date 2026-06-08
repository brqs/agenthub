import { AlertTriangle, CheckCircle2, Clock3, Loader2, Rocket, Square } from 'lucide-react';
import type { DeploymentStatusBlock, WorkspaceDeploymentResponse } from '@/lib/types';

export type DeploymentKind = WorkspaceDeploymentResponse['kind'];
export type DeploymentStatus = WorkspaceDeploymentResponse['status'];
export type DeploymentLike = Partial<WorkspaceDeploymentResponse> &
  Partial<DeploymentStatusBlock> & {
    kind: DeploymentKind;
    status: DeploymentStatus;
  };

export const DEPLOYMENT_KIND_LABELS: Record<DeploymentKind, string> = {
  static_site: '静态站点',
  source_zip: '源码包',
  container: '容器部署',
};

export const DEPLOYMENT_STATUS_META = {
  queued: {
    label: '排队中',
    icon: Clock3,
    className:
      'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-400/25 dark:bg-sky-400/10 dark:text-sky-200',
  },
  publishing: {
    label: '发布中',
    icon: Loader2,
    className:
      'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200',
  },
  published: {
    label: '已发布',
    icon: CheckCircle2,
    className:
      'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/25 dark:bg-emerald-400/10 dark:text-emerald-300',
  },
  failed: {
    label: '发布失败',
    icon: AlertTriangle,
    className:
      'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-400/25 dark:bg-rose-400/10 dark:text-rose-300',
  },
  stopped: {
    label: '已停止',
    icon: Square,
    className:
      'border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
  },
  not_supported: {
    label: '暂不支持',
    icon: AlertTriangle,
    className:
      'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-400/25 dark:bg-sky-400/10 dark:text-sky-200',
  },
} as const;

export const DEPLOYMENT_ACTIONS: Array<{
  kind: DeploymentKind;
  label: string;
  description: string;
  icon: typeof Rocket;
}> = [
  {
    kind: 'static_site',
    label: '发布静态站点',
    description: '生成稳定预览 URL',
    icon: Rocket,
  },
  {
    kind: 'source_zip',
    label: '打包源码',
    description: '导出安全源码 zip',
    icon: CheckCircle2,
  },
  {
    kind: 'container',
    label: '容器化部署',
    description: '平台 worker 构建运行',
    icon: Loader2,
  },
];

export function deploymentTitle(deployment: Pick<DeploymentLike, 'kind' | 'title'>): string {
  return deployment.title ?? `${DEPLOYMENT_KIND_LABELS[deployment.kind]}发布`;
}

export function formatBytes(size?: number | null): string | null {
  if (!size) return null;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDateTime(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString();
}

export function isDeploymentInProgress(status: DeploymentStatus): boolean {
  return status === 'queued' || status === 'publishing';
}

export function buildDeploymentTimeline(deployment: DeploymentLike) {
  const eventTimeline = deploymentEvents(deployment);
  if (eventTimeline.length) return eventTimeline;

  const terminalLabel =
    deployment.status === 'failed'
      ? '失败'
      : deployment.status === 'stopped'
        ? '停止'
        : deployment.status === 'not_supported'
          ? '环境不支持'
          : '完成';

  return [
    {
      key: 'queued',
      label: '已创建发布任务',
      time: deployment.queued_at ?? deployment.created_at,
      active: true,
    },
    {
      key: 'publishing',
      label: deployment.kind === 'container' ? '构建并启动容器' : '生成发布产物',
      time: deployment.started_at,
      active: ['publishing', 'published', 'failed', 'stopped'].includes(deployment.status),
    },
    {
      key: 'healthcheck',
      label: deployment.kind === 'container' ? '健康检查' : '发布可访问性检查',
      time: deployment.last_checked_at,
      active:
        deployment.kind === 'container' &&
        ['publishing', 'published', 'failed', 'stopped'].includes(deployment.status),
    },
    {
      key: 'terminal',
      label: terminalLabel,
      time:
        deployment.completed_at ??
        deployment.published_at ??
        deployment.stopped_at ??
        deployment.updated_at,
      active: ['published', 'failed', 'stopped', 'not_supported'].includes(deployment.status),
    },
  ].filter((step) => step.active);
}

function deploymentEvents(deployment: DeploymentLike) {
  const events = Array.isArray(deployment.state_events) ? deployment.state_events : [];
  return events
    .map((event, index) => {
      if (!event || typeof event !== 'object') return null;
      const payload = event as Record<string, unknown>;
      const timestamp = typeof payload.timestamp === 'string' ? payload.timestamp : null;
      const type = typeof payload.type === 'string' ? payload.type : 'event';
      return {
        key: `${type}-${index}`,
        label: deploymentEventLabel(payload),
        time: timestamp,
        active: true,
      };
    })
    .filter((step): step is { key: string; label: string; time: string | null; active: boolean } =>
      Boolean(step),
    )
    .slice(-6);
}

function deploymentEventLabel(event: Record<string, unknown>) {
  const type = typeof event.type === 'string' ? event.type : 'event';
  if (type === 'status_changed') {
    const to =
      typeof event.to === 'string'
        ? DEPLOYMENT_STATUS_META[event.to as DeploymentStatus]?.label
        : null;
    return to ? `状态更新：${to}` : '状态已更新';
  }
  if (type === 'worker_submitted') return 'Worker 已接收';
  if (type === 'stop_requested') return '已请求停止';
  if (type === 'health_checked') return '健康检查完成';
  return type.replaceAll('_', ' ');
}
