import { X } from 'lucide-react';
import { env } from '@/lib/env';
import { useUiStore, type SystemTheme, type ThemeMode, type ThemePreference } from '@/stores/uiStore';

export function SettingsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const themePreference = useUiStore((s) => s.themePreference);
  const resolvedTheme = useUiStore((s) => s.resolvedTheme);
  const systemTheme = useUiStore((s) => s.systemTheme);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 backdrop-blur-sm">
      <section className="w-full max-w-lg overflow-hidden rounded-md border border-slate-300 bg-white shadow-2xl shadow-black/20 dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/40">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div>
            <h2 className="text-base font-semibold text-slate-950 dark:text-white">Settings</h2>
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

        <div className="space-y-3 p-5">
          <SettingRow label="主题偏好" value={formatThemePreference(themePreference)} />
          <SettingRow label="当前生效" value={formatResolvedTheme(resolvedTheme)} />
          <SettingRow label="系统主题" value={formatSystemTheme(systemTheme)} />
          <SettingRow label="API 模式" value="Real" />
          <SettingRow label="SSE 模式" value="Real" />
          <SettingRow label="Base URL" value={env.apiBaseUrl || 'Vite /api proxy'} />
          <SettingRow label="本地演示数据" value="Disabled" />
          <SettingRow label="Build" value="frontend-api" />
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

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-950/70">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="min-w-0 truncate text-sm font-medium text-slate-900 dark:text-slate-200">{value}</span>
    </div>
  );
}
