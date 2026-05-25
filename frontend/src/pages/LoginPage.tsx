import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, extractApiError } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';
import type { AuthResponse } from '@/lib/types';

export function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();

  function enterDemo() {
    setAuth('mock-demo-token', {
      id: '00000000-0000-4000-8000-000000000001',
      username: 'frontend-demo',
      avatar_url: null,
      created_at: new Date().toISOString(),
    });
    navigate('/chat');
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const url = mode === 'login' ? '/api/v1/auth/login' : '/api/v1/auth/register';
      const { data } = await api.post<AuthResponse>(url, { username, password });
      setAuth(data.access_token, data.user);
      navigate('/chat');
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-slate-900 px-4">
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
          <button
            type="button"
            onClick={enterDemo}
            className="w-full rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            进入前端 Demo
          </button>
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
      </div>
    </div>
  );
}
