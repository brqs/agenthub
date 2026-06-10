import {
  AlertTriangle,
  CheckCircle2,
  FolderOpen,
  Loader2,
  Monitor,
  Play,
  RefreshCw,
  WifiOff,
  Wrench,
} from 'lucide-react';
import type {
  DesktopBackendHealth,
  DesktopBridgeError,
  DesktopLocalStackStatus,
  DesktopStackProgress,
} from '@/lib/desktopBridge';
import type { DesktopCheckState } from '@/hooks/useDesktopEnvironment';
import { DesktopLogsPanel } from './DesktopLogsPanel';
import { DesktopBackendProfilesPanel } from './DesktopBackendProfilesPanel';

interface DesktopStartupScreenProps {
  backendUrl: string;
  checkState: DesktopCheckState;
  health: DesktopBackendHealth | null;
  stackStatus: DesktopLocalStackStatus | null;
  stackProgress: DesktopStackProgress | null;
  desktopError: DesktopBridgeError | null;
  operationPending: boolean;
  localMode: boolean;
  onBackendUrlChange: (url: string) => void;
  onRetry: () => void;
  onChooseProjectRoot: () => void;
  onStart: () => void;
  onRebuild: () => void;
}

export function DesktopStartupScreen({
  backendUrl,
  checkState,
  health,
  stackStatus,
  stackProgress,
  desktopError,
  operationPending,
  localMode,
  onBackendUrlChange,
  onRetry,
  onChooseProjectRoot,
  onStart,
  onRebuild,
}: DesktopStartupScreenProps) {
  const checking = checkState === 'checking' || operationPending;
  const connected = checkState === 'ready';
  const failed = checkState === 'unreachable';
  const needsRebuild = desktopError?.code === 'backend_image_missing';

  return (
    <main className="flex min-h-[100dvh] items-center justify-center bg-slate-100 px-4 py-8 text-slate-950 dark:bg-slate-950 dark:text-white">
      <section className="w-full max-w-2xl rounded-md border border-slate-300 bg-white p-6 shadow-xl shadow-slate-950/10 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-indigo-100 p-2 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300">
            {failed ? <WifiOff className="h-5 w-5" /> : <Monitor className="h-5 w-5" />}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-indigo-500">
              AgentHub Desktop
            </p>
            <h1 className="mt-1 text-xl font-semibold">连接 AgentHub 后端</h1>
            <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
              {checking
                ? stackProgress?.message || '正在检查本地后端服务...'
                : connected
                  ? '后端已连接，正在进入 AgentHub。'
                  : '还没有连接到 AgentHub 后端。你可以启动本地服务，也可以连接已有后端。'}
            </p>
          </div>
        </div>

        {localMode && (
          <div className="mt-5 divide-y divide-slate-200 border-y border-slate-200 text-sm dark:divide-slate-800 dark:border-slate-800">
            <StatusRow
              label="项目目录"
              value={stackStatus?.projectRoot || '尚未识别'}
              ready={Boolean(stackStatus?.projectRoot)}
            />
            <StatusRow
              label="Docker"
              value={formatDockerStatus(stackStatus?.docker)}
              ready={stackStatus?.docker === 'ready'}
            />
            <StatusRow
              label="本地服务"
              value={formatServices(stackStatus)}
              ready={stackStatus?.backendHealth === 'ready'}
            />
          </div>
        )}

        <label className="mt-6 block text-sm font-medium text-slate-700 dark:text-slate-200">
          后端地址
          <input
            value={backendUrl}
            onChange={(event) => onBackendUrlChange(event.target.value)}
            className="mt-2 w-full rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-950"
            placeholder="http://localhost:8000"
            disabled={checking}
          />
        </label>

        <DesktopBackendProfilesPanel compact />

        {failed && (
          <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-200">
            {desktopError?.message || health?.error || '无法连接到后端。'}
            {desktopError?.detail && <p className="mt-1 text-xs">{desktopError.detail}</p>}
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-2">
          {localMode && (
            <button
              type="button"
              onClick={onStart}
              disabled={checking}
              className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {operationPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {operationPending ? '正在启动' : '启动本地 AgentHub'}
            </button>
          )}
          {localMode && needsRebuild && (
            <button
              type="button"
              onClick={onRebuild}
              disabled={checking}
              className="inline-flex items-center gap-2 rounded-md border border-amber-300 px-4 py-2 text-sm font-medium text-amber-800 hover:bg-amber-50 disabled:opacity-60 dark:border-amber-500/50 dark:text-amber-200 dark:hover:bg-amber-500/10"
            >
              <Wrench className="h-4 w-4" />
              重新构建并启动
            </button>
          )}
          <button
            type="button"
            onClick={onRetry}
            disabled={checking}
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <RefreshCw className="h-4 w-4" />
            重试连接
          </button>
          {localMode && (
            <button
              type="button"
              onClick={onChooseProjectRoot}
              disabled={checking}
              className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <FolderOpen className="h-4 w-4" />
              选择项目目录
            </button>
          )}
        </div>

        {localMode && <DesktopLogsPanel />}
      </section>
    </main>
  );
}

function StatusRow({ label, value, ready }: { label: string; value: string; ready: boolean }) {
  return (
    <div className="flex min-h-10 items-center gap-3 py-2">
      {ready ? (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
      ) : (
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
      )}
      <span className="w-20 shrink-0 text-slate-500">{label}</span>
      <span className="min-w-0 truncate font-medium text-slate-800 dark:text-slate-200" title={value}>
        {value}
      </span>
    </div>
  );
}

function formatDockerStatus(status: DesktopLocalStackStatus['docker'] | undefined): string {
  if (status === 'ready') return '已就绪';
  if (status === 'not_installed') return '未安装 Docker Desktop';
  if (status === 'not_running') return 'Docker Desktop 未运行';
  return '正在检查';
}

function formatServices(status: DesktopLocalStackStatus | null): string {
  if (!status) return '正在检查';
  if (status.backendHealth === 'ready') return 'Backend 已就绪';
  const running = status.services.filter((service) =>
    ['healthy', 'running', 'starting'].includes(service.status),
  ).length;
  return running ? `${running}/3 个服务已启动` : '尚未启动';
}
