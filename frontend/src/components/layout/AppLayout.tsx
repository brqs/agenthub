import { Outlet } from 'react-router-dom';
import { ModuleRail } from './ModuleRail';
import { useAuthStore } from '@/stores/authStore';

export function AppLayout() {
  const logout = useAuthStore((s) => s.logout);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100">
      <ModuleRail onLogout={logout} />
      <main className="min-w-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
