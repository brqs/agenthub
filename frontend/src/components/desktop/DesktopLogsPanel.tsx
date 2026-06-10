import { useState } from 'react';
import { Download, Loader2, RefreshCw } from 'lucide-react';
import {
  exportDesktopDiagnostics,
  normalizeDesktopError,
  saveDesktopDiagnostics,
  tailDesktopServiceLogs,
  type DesktopBridgeError,
  type DesktopDiagnosticsExport,
  type DesktopServiceLogTail,
  type DesktopServiceName,
} from '@/lib/desktopBridge';

const SERVICES: Array<{ id: DesktopServiceName; label: string }> = [
  { id: 'backend', label: 'Backend' },
  { id: 'postgres', label: 'Postgres' },
  { id: 'redis', label: 'Redis' },
];

export function DesktopLogsPanel({ compact = false }: { compact?: boolean }) {
  const [service, setService] = useState<DesktopServiceName>('backend');
  const [logs, setLogs] = useState<DesktopServiceLogTail | null>(null);
  const [error, setError] = useState<DesktopBridgeError | null>(null);
  const [loading, setLoading] = useState(false);
  const [diagnostics, setDiagnostics] = useState<DesktopDiagnosticsExport | null>(null);
  const [diagnosticsSaved, setDiagnosticsSaved] = useState('');

  const loadLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      setLogs(await tailDesktopServiceLogs(service));
    } catch (nextError) {
      setError(normalizeDesktopError(nextError));
    } finally {
      setLoading(false);
    }
  };

  const exportDiagnostics = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await exportDesktopDiagnostics();
      setDiagnostics(result);
      setDiagnosticsSaved('');
    } catch (nextError) {
      setError(normalizeDesktopError(nextError));
    } finally {
      setLoading(false);
    }
  };

  const saveDiagnostics = async () => {
    if (!diagnostics) return;
    setLoading(true);
    setError(null);
    try {
      const result = await saveDesktopDiagnostics(diagnostics.fileToken);
      setDiagnosticsSaved(result.saved ? result.fileName ?? diagnostics.suggestedName : '');
    } catch (nextError) {
      setError(normalizeDesktopError(nextError));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className={compact ? 'space-y-3' : 'mt-5 border-t border-slate-200 pt-4 dark:border-slate-800'}>
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm font-medium text-slate-700 dark:text-slate-200">
          服务日志
          <select
            value={service}
            onChange={(event) => setService(event.target.value as DesktopServiceName)}
            className="ml-2 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            {SERVICES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={loadLogs}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          刷新日志
        </button>
        <button
          type="button"
          onClick={exportDiagnostics}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          <Download className="h-4 w-4" />
          导出诊断
        </button>
      </div>

      {error && (
        <p className="text-sm text-rose-700 dark:text-rose-300">
          {error.message}
          {error.detail ? ` ${error.detail}` : ''}
        </p>
      )}
      {diagnostics && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200">
          <span>诊断信息已生成：{diagnostics.suggestedName}</span>
          <button
            type="button"
            onClick={() => void saveDiagnostics()}
            disabled={loading}
            className="rounded-md border border-emerald-300 bg-white px-2 py-1 font-medium hover:bg-emerald-100 disabled:opacity-50 dark:border-emerald-500/40 dark:bg-emerald-950/30 dark:hover:bg-emerald-900/40"
          >
            另存为
          </button>
          {diagnosticsSaved && <span>已保存：{diagnosticsSaved}</span>}
        </div>
      )}
      {logs && (
        <pre className="max-h-56 overflow-auto rounded-md bg-slate-950 p-3 text-xs leading-5 text-slate-100 scrollbar-thin">
          {logs.lines.length ? logs.lines.join('\n') : '当前没有日志。'}
        </pre>
      )}
    </section>
  );
}
