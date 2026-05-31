import { X } from 'lucide-react';
import { env } from '@/lib/env';

export function SettingsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 backdrop-blur-sm">
      <section className="w-full max-w-lg overflow-hidden rounded-md border border-slate-700 bg-slate-900 shadow-2xl shadow-black/40">
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-white">Settings</h2>
            <p className="mt-1 text-xs text-slate-500">当前运行状态</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 transition hover:bg-slate-800 hover:text-white"
            title="关闭"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="space-y-3 p-5">
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

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-slate-800 bg-slate-950/70 px-3 py-2">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="min-w-0 truncate text-sm font-medium text-slate-200">{value}</span>
    </div>
  );
}
