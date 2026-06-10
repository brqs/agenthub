import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DesktopBackendProfilesPanel } from '@/components/desktop/DesktopBackendProfilesPanel';
import { useDesktopEnvironment } from '@/hooks/useDesktopEnvironment';
import { extractApiError } from '@/lib/api';
import * as authAdapter from '@/lib/adapters/auth';
import { startClientSession } from '@/lib/session';

export function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const desktop = useDesktopEnvironment();
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data =
        mode === 'login'
          ? await authAdapter.login({ username, password, platform: 'web' })
          : await authAdapter.register({ username, password, platform: 'web' });
      startClientSession(data.access_token, data.user, {
        refreshToken: data.refresh_token ?? null,
        sessionId: data.session?.id ?? null,
        expiresIn: data.expires_in ?? null,
      });
      navigate('/chat');
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen min-h-[100dvh] items-center justify-center bg-gray-50 px-4 dark:bg-slate-900">
      <div className="w-full max-w-md p-8 bg-white dark:bg-slate-800 rounded-xl shadow-md">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🤖</div>
          <h1 className="text-2xl font-bold">AgentHub</h1>
          <p className="text-sm text-gray-500 dark:text-slate-400 mt-1">
            Multi-Agent Collaboration Platform
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="text"
            placeholder="用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-4 py-2 rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-brand"
            required
            minLength={3}
          />
          <input
            type="password"
            placeholder="密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-4 py-2 rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-brand"
            required
            minLength={8}
          />

          {error && (
            <div className="text-sm text-red-600 dark:text-red-400">{error}</div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-brand hover:bg-brand-hover text-white rounded-md font-medium transition disabled:opacity-50"
          >
            {loading ? '...' : mode === 'login' ? '登 录' : '注 册'}
          </button>
          <p className="text-center text-xs text-slate-500">
            请使用真实账号登录。
          </p>
        </form>

        <div className="text-center mt-6 text-sm text-gray-500 dark:text-slate-400">
          {mode === 'login' ? '没有账号？' : '已有账号？'}{' '}
          <button
            type="button"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login');
              setError(null);
            }}
            className="text-brand hover:underline"
          >
            {mode === 'login' ? '立即注册' : '去登录'}
          </button>
        </div>

        {desktop.isDesktop && (
          <details className="mt-5 rounded-md border border-slate-200 bg-slate-50/80 p-3 text-left dark:border-slate-700 dark:bg-slate-900/50">
            <summary className="cursor-pointer list-none">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    后端连接
                  </p>
                  <p
                    className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400"
                    title={desktop.runtimeApiBaseUrl}
                  >
                    当前：{desktop.runtimeApiBaseUrl}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                    desktop.checkState === 'ready'
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200'
                      : desktop.checkState === 'checking'
                        ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-200'
                        : 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                  }`}
                >
                  {desktop.checkState === 'ready'
                    ? '已连接'
                    : desktop.checkState === 'checking'
                      ? '检测中'
                      : '可切换'}
                </span>
              </div>
            </summary>
            <DesktopBackendProfilesPanel compact />
          </details>
        )}
      </div>
    </div>
  );
}
