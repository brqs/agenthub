import {
  AlertTriangle,
  CheckCircle2,
  FolderOpen,
  Loader2,
  Play,
  RefreshCw,
  RotateCw,
  Square,
  Wrench,
} from 'lucide-react';
import type { DesktopEnvironmentState } from '@/hooks/useDesktopEnvironment';
import { isLocalBackendUrl, type DesktopDockerStatus } from '@/lib/desktopBridge';
import { DesktopLogsPanel } from './DesktopLogsPanel';

export function DesktopLocalStackPanel({ desktop }: { desktop: DesktopEnvironmentState }) {
  const localMode = isLocalBackendUrl(desktop.backendUrl);
  const busy = desktop.operationPending;

  const confirmStart = () => {
    if (!window.confirm('启动 AgentHub 本地服务？此操作不会删除数据卷。')) return;
    desktop.startLocalStack().catch(() => undefined);
  };

  const confirmStop = () => {
    if (!window.confirm('停止 Backend、Postgres 和 Redis？数据卷会被保留。')) return;
    desktop.stopLocalStack().catch(() => undefined);
  };

  const confirmRebuild = () => {
    if (
      !window.confirm(
        '当前缺少 Backend 镜像。确认联网重新构建镜像并启动吗？已有数据库和运行时数据卷不会被删除。',
      )
    ) {
      return;
    }
    desktop.startLocalStack(true).catch(() => undefined);
  };

  const confirmRestart = () => {
    if (!window.confirm('重启 AgentHub Backend？正在进行的流式任务可能中断。')) return;
    desktop.restartBackend().catch(() => undefined);
  };

  return (
    <section className="border-t border-slate-200 pt-4 dark:border-slate-800">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">本地服务</h3>
          <p className="mt-1 text-xs text-slate-500">
            仅管理已识别的 AgentHub Docker 栈，不会删除数据库或运行时数据卷。
          </p>
        </div>
        <button
          type="button"
          onClick={() => desktop.refreshLocalStack().catch(() => undefined)}
          disabled={busy}
          className="rounded-md border border-slate-300 p-2 text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          title="刷新状态"
          aria-label="刷新本地服务状态"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {!localMode ? (
        <p className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
          当前连接的是远程后端，本地 Docker 控制已隐藏。
        </p>
      ) : (
        <>
          <div className="mt-3 divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-800 dark:border-slate-800">
            <StatusRow
              label="项目目录"
              value={desktop.stackStatus?.projectRoot || '尚未识别'}
              ready={Boolean(desktop.stackStatus?.projectRoot)}
            />
            <StatusRow
              label="Docker"
              value={formatDocker(desktop.stackStatus?.docker)}
              ready={desktop.stackStatus?.docker === 'ready'}
            />
            {(['postgres', 'redis', 'backend'] as const).map((name) => {
              const service = desktop.stackStatus?.services.find((item) => item.name === name);
              return (
                <StatusRow
                  key={name}
                  label={name === 'backend' ? 'Backend' : name === 'postgres' ? 'Postgres' : 'Redis'}
                  value={formatService(service?.status)}
                  ready={service?.status === 'healthy' || service?.status === 'running'}
                />
              );
            })}
          </div>

          {desktop.stackProgress && (
            <p className="mt-3 flex items-center gap-2 text-sm text-indigo-700 dark:text-indigo-300">
              <Loader2 className="h-4 w-4 animate-spin" />
              {desktop.stackProgress.message}
            </p>
          )}
          {desktop.desktopError && (
            <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-200">
              {desktop.desktopError.message}
              {desktop.desktopError.detail && (
                <p className="mt-1 break-words text-xs">{desktop.desktopError.detail}</p>
              )}
            </div>
          )}

          <div className="mt-3 flex flex-wrap gap-2">
            <ActionButton icon={Play} label="启动" onClick={confirmStart} disabled={busy} primary />
            <ActionButton icon={Square} label="停止" onClick={confirmStop} disabled={busy} />
            <ActionButton
              icon={RotateCw}
              label="重启 Backend"
              onClick={confirmRestart}
              disabled={busy}
            />
            <ActionButton
              icon={FolderOpen}
              label="选择项目目录"
              onClick={() => desktop.chooseProjectRoot().catch(() => undefined)}
              disabled={busy}
            />
            {desktop.desktopError?.code === 'backend_image_missing' && (
              <ActionButton
                icon={Wrench}
                label="重新构建并启动"
                onClick={confirmRebuild}
                disabled={busy}
              />
            )}
          </div>

          <label className="mt-4 flex items-start gap-3 text-sm text-slate-700 dark:text-slate-200">
            <input
              type="checkbox"
              checked={Boolean(desktop.preferences?.autoStartLocalStack)}
              onChange={(event) =>
                desktop
                  .updatePreferences({ autoStartLocalStack: event.target.checked })
                  .catch(() => undefined)
              }
              className="mt-0.5 h-4 w-4 accent-indigo-600"
            />
            <span>
              启动桌面客户端时自动恢复本地服务
              <span className="mt-1 block text-xs text-slate-500">
                默认关闭。开启后仅执行受控的 Docker Compose 启动流程。
              </span>
            </span>
          </label>

          <div className="mt-4">
            <DesktopLogsPanel compact />
          </div>
        </>
      )}
    </section>
  );
}

function StatusRow({ label, value, ready }: { label: string; value: string; ready: boolean }) {
  return (
    <div className="flex min-h-10 items-center gap-3 py-2 text-sm">
      {ready ? (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
      ) : (
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
      )}
      <span className="w-24 shrink-0 text-slate-500">{label}</span>
      <span className="min-w-0 truncate font-medium text-slate-900 dark:text-slate-200" title={value}>
        {value}
      </span>
    </div>
  );
}

function ActionButton({
  icon: Icon,
  label,
  onClick,
  disabled,
  primary = false,
}: {
  icon: typeof Play;
  label: string;
  onClick: () => void;
  disabled: boolean;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={
        primary
          ? 'inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50'
          : 'inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800'
      }
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );
}

function formatDocker(status: DesktopDockerStatus | undefined) {
  if (status === 'ready') return '已就绪';
  if (status === 'not_installed') return '未安装 Docker Desktop';
  if (status === 'not_running') return 'Docker Desktop 未运行';
  return '正在检查';
}

function formatService(status: string | undefined) {
  if (status === 'healthy') return '健康';
  if (status === 'running') return '运行中';
  if (status === 'starting') return '启动中';
  if (status === 'error') return '异常';
  return '已停止';
}
