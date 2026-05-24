import { Outlet, Link } from 'react-router-dom';
import { MessageSquare, Bot, LogOut } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';

export function AppLayout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      {/* L1 模块导航（窄列） */}
      <nav className="w-16 flex flex-col items-center gap-3 py-4 border-r border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-900">
        <div className="text-2xl">🤖</div>
        <Link
          to="/chat"
          className="p-2 rounded hover:bg-gray-200 dark:hover:bg-slate-800"
          title="聊天"
        >
          <MessageSquare className="w-5 h-5" />
        </Link>
        <Link
          to="/agents"
          className="p-2 rounded hover:bg-gray-200 dark:hover:bg-slate-800"
          title="Agent"
        >
          <Bot className="w-5 h-5" />
        </Link>
        <div className="flex-1" />
        <button
          onClick={logout}
          className="p-2 rounded hover:bg-gray-200 dark:hover:bg-slate-800"
          title={`登出 (${user?.username})`}
        >
          <LogOut className="w-5 h-5" />
        </button>
      </nav>

      {/* 主内容 */}
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
