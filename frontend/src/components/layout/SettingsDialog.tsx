import { ExternalLink, Monitor, RefreshCw, X } from 'lucide-react';
import { DesktopLocalStackPanel } from '@/components/desktop/DesktopLocalStackPanel';
import { useDesktopEnvironment } from '@/hooks/useDesktopEnvironment';
import { env } from '@/lib/env';
import { useUiStore, type SystemTheme, type ThemeMode, type ThemePreference } from '@/stores/uiStore';

export function SettingsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const themePreference = useUiStore((s) => s.themePreference);
  const resolvedTheme = useUiStore((s) => s.resolvedTheme);
  const systemTheme = useUiStore((s) => s.systemTheme);
  const desktop = useDesktopEnvironment();
  const updateBusy = desktop.updateState === 'checking' || desktop.updateState === 'installing';

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 sm:px-4 sm:py-6 backdrop-blur-sm">
      <section className="flex h-[100dvh] w-full max-w-lg flex-col overflow-hidden border border-slate-300 bg-white shadow-2xl shadow-black/20 dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/40 sm:h-auto sm:max-h-[calc(100dvh-3rem)] sm:rounded-md">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div>
            <h2 className="text-base font-semibold text-slate-950 dark:text-white">设置</h2>
            <p className="mt-1 text-xs text-slate-500">当前运行状态</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
            title="关闭"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-5 scrollbar-thin">
          <SettingRow label="主题偏好" value={formatThemePreference(themePreference)} />
          <SettingRow label="当前生效" value={formatResolvedTheme(resolvedTheme)} />
          <SettingRow label="系统主题" value={formatSystemTheme(systemTheme)} />
          <SettingRow label="API 模式" value="真实后端" />
          <SettingRow label="SSE 模式" value="真实流式输出" />
          <SettingRow label="后端地址" value={env.apiBaseUrl || 'Vite /api 代理'} />
          <SettingRow label="本地演示数据" value="已关闭" />
          <SettingRow label="构建类型" value="frontend-api" />

          {desktop.isDesktop && (
            <section className="rounded-md border border-indigo-200 bg-indigo-50 p-3 dark:border-indigo-500/30 dark:bg-indigo-500/10">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-indigo-700 dark:text-indigo-200">
                <Monitor className="h-4 w-4" />
                桌面客户端
              </div>
              <div className="space-y-2">
                <SettingRow compact label="运行环境" value="Windows 桌面壳" />
                <SettingRow compact label="连接状态" value={formatDesktopCheckState(desktop.checkState)} />
                <SettingRow compact label="后端地址" value={desktop.runtimeApiBaseUrl || desktop.backendUrl} />
                <SettingRow
                  compact
                  label="桌面版本"
                  value={desktop.releaseInfo?.appVersion || desktop.environment?.appVersion || '未知'}
                />
                {desktop.health?.version && (
                  <SettingRow compact label="后端版本" value={desktop.health.version} />
                )}
              </div>
              <div className="mt-4 rounded-md border border-white/70 bg-white/70 p-3 dark:border-slate-700/60 dark:bg-slate-950/35">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      版本与更新
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-slate-500">
                      {formatDesktopUpdateState(desktop.updateState, desktop.updateCheck)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => desktop.openReleasePage().catch(() => undefined)}
                    className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    发布页
                  </button>
                </div>
                <div className="mt-3 space-y-2">
                  <SettingRow
                    compact
                    label="上次检查"
                    value={formatLastCheckedAt(
                      desktop.preferences?.lastUpdateCheckAt || desktop.releaseInfo?.lastUpdateCheckAt,
                    )}
                  />
                  <SettingRow
                    compact
                    label="更新通道"
                    value={desktop.releaseInfo?.updateChannel === 'stable' ? '稳定版' : '稳定版'}
                  />
                </div>
                {desktop.updateError && (
                  <p className="mt-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-200">
                    {desktop.updateError.message}
                  </p>
                )}
                <label className="mt-3 flex items-start gap-3 text-sm text-slate-700 dark:text-slate-200">
                  <input
                    type="checkbox"
                    checked={desktop.preferences?.autoCheckUpdates !== false}
                    onChange={(event) =>
                      desktop
                        .updatePreferences({ autoCheckUpdates: event.target.checked })
                        .catch(() => undefined)
                    }
                    className="mt-0.5 h-4 w-4 accent-indigo-600"
                  />
                  <span>
                    自动检查更新
                    <span className="mt-1 block text-xs leading-5 text-slate-500">
                      默认开启。检查失败不会阻塞登录、聊天或本地服务管理。
                    </span>
                  </span>
                </label>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => desktop.checkForUpdate().catch(() => undefined)}
                    disabled={updateBusy}
                    className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <RefreshCw className={updateBusy ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
                    检查更新
                  </button>
                  {desktop.updateState === 'available' && (
                    <button
                      type="button"
                      onClick={() => desktop.installUpdate().catch(() => undefined)}
                      disabled={updateBusy}
                      className="rounded-md border border-emerald-300 px-3 py-2 text-xs font-medium text-emerald-800 transition hover:bg-emerald-50 disabled:opacity-60 dark:border-emerald-500/40 dark:text-emerald-200 dark:hover:bg-emerald-500/10"
                    >
                      下载并安装
                    </button>
                  )}
                </div>
              </div>
              <label className="mt-4 flex items-start gap-3 rounded-md bg-white/70 px-3 py-3 text-sm text-slate-700 dark:bg-slate-950/40 dark:text-slate-200">
                <input
                  type="checkbox"
                  checked={Boolean(desktop.preferences?.notificationsEnabled)}
                  onChange={(event) =>
                    desktop
                      .updatePreferences({ notificationsEnabled: event.target.checked })
                      .catch(() => undefined)
                  }
                  className="mt-0.5 h-4 w-4 accent-indigo-600"
                />
                <span>
                  系统通知
                  <span className="mt-1 block text-xs leading-5 text-slate-500">
                    默认关闭。开启后，后台会话完成、失败或等待确认时会发送不含聊天正文的通知。
                  </span>
                </span>
              </label>
              <div className="mt-4">
                <DesktopLocalStackPanel desktop={desktop} />
              </div>
            </section>
          )}
        </div>
      </section>
    </div>
  );
}

function formatThemePreference(preference: ThemePreference): string {
  if (preference === 'system') return '跟随系统';
  return formatResolvedTheme(preference);
}

function formatResolvedTheme(theme: ThemeMode): string {
  return theme === 'dark' ? '深色' : '浅色';
}

function formatSystemTheme(theme: SystemTheme): string {
  return theme === 'unknown' ? '未知' : formatResolvedTheme(theme);
}

function formatDesktopCheckState(state: string): string {
  if (state === 'checking') return '正在检查';
  if (state === 'ready') return '已连接';
  if (state === 'unreachable') return '未连接';
  return '待检查';
}

function formatDesktopUpdateState(
  state: string,
  check: { version?: string; available?: boolean } | null,
): string {
  if (state === 'checking') return '正在检查更新';
  if (state === 'installing') return '正在下载并安装更新';
  if (state === 'available') return check?.version ? `发现新版本 ${check.version}` : '发现新版本';
  if (state === 'current') return '当前已经是最新版本';
  if (state === 'restart_required') return '更新已安装，重启应用后生效';
  if (state === 'error') return '更新检查失败';
  return '尚未检查更新';
}

function formatLastCheckedAt(value: string | undefined): string {
  if (!value) return '尚未检查';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN');
}

function SettingRow({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: string;
  compact?: boolean;
}) {
  return (
    <div
      className={
        compact
          ? 'flex items-center justify-between gap-4 rounded-md bg-white/70 px-3 py-2 dark:bg-slate-950/40'
          : 'flex items-center justify-between gap-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-950/70'
      }
    >
      <span className="text-sm text-slate-500">{label}</span>
      <span className="min-w-0 truncate text-sm font-medium text-slate-900 dark:text-slate-200">{value}</span>
    </div>
  );
}
