import { MonitorSmartphone, RefreshCw, Trash2 } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as authAdapter from '@/lib/adapters/auth';

const DEVICE_SESSIONS_QUERY_KEY = ['auth', 'sessions'] as const;

export function DeviceSessionsPanel() {
  const queryClient = useQueryClient();
  const sessionsQuery = useQuery({
    queryKey: DEVICE_SESSIONS_QUERY_KEY,
    queryFn: authAdapter.listSessions,
    staleTime: 30_000,
  });

  const revokeMutation = useMutation({
    mutationFn: authAdapter.revokeSession,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DEVICE_SESSIONS_QUERY_KEY }),
  });

  const revokeOthersMutation = useMutation({
    mutationFn: authAdapter.revokeOtherSessions,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DEVICE_SESSIONS_QUERY_KEY }),
  });

  const sessions = sessionsQuery.data?.items ?? [];
  const busy = revokeMutation.isPending || revokeOthersMutation.isPending;

  return (
    <section className="rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950/70">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2">
          <MonitorSmartphone className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" />
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">登录设备</h3>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              这里显示当前后端账号的设备会话。远程注销后，对方设备会在令牌刷新失败时退出登录。
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => sessionsQuery.refetch()}
          disabled={sessionsQuery.isFetching}
          className="rounded-md p-1.5 text-slate-500 transition hover:bg-white hover:text-slate-900 disabled:opacity-50 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          aria-label="刷新登录设备"
          title="刷新登录设备"
        >
          <RefreshCw className={sessionsQuery.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
        </button>
      </div>

      {sessionsQuery.isError && (
        <p className="mt-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-200">
          登录设备加载失败，请稍后重试。
        </p>
      )}

      <div className="mt-3 space-y-2">
        {sessions.length === 0 && !sessionsQuery.isLoading ? (
          <p className="rounded-md border border-dashed border-slate-300 px-3 py-3 text-xs text-slate-500 dark:border-slate-700">
            暂无设备会话。
          </p>
        ) : null}
        {sessions.map((session) => (
          <div
            key={session.id}
            className="flex items-center justify-between gap-3 rounded-md border border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                  {session.device_name}
                </span>
                {session.is_current && (
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200">
                    当前设备
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {formatPlatform(session.platform)} · 最近活跃 {formatDateTime(session.last_active_at)}
              </p>
            </div>
            {!session.is_current && (
              <button
                type="button"
                onClick={() => revokeMutation.mutate(session.id)}
                disabled={busy}
                className="inline-flex shrink-0 items-center gap-1 rounded-md border border-rose-200 px-2 py-1 text-xs font-medium text-rose-700 transition hover:bg-rose-50 disabled:opacity-50 dark:border-rose-500/40 dark:text-rose-200 dark:hover:bg-rose-500/10"
              >
                <Trash2 className="h-3.5 w-3.5" />
                注销
              </button>
            )}
          </div>
        ))}
      </div>

      {sessions.some((session) => !session.is_current) && (
        <button
          type="button"
          onClick={() => revokeOthersMutation.mutate()}
          disabled={busy}
          className="mt-3 rounded-md border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-white disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-900"
        >
          注销其他设备
        </button>
      )}
    </section>
  );
}

function formatPlatform(platform: string): string {
  if (platform === 'desktop') return '桌面端';
  if (platform === 'ios') return 'iOS';
  if (platform === 'android') return 'Android';
  return 'Web';
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN');
}
