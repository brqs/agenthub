import { Outlet } from 'react-router-dom';
import { ModuleRail } from './ModuleRail';
import { SettingsDialog } from './SettingsDialog';
import { UserMenu } from './UserMenu';
import { useAuthStore } from '@/stores/authStore';
import { useUiStore } from '@/stores/uiStore';

export function AppLayout() {
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);
  const theme = useUiStore((s) => s.theme);
  const settingsOpen = useUiStore((s) => s.settingsOpen);
  const userMenuOpen = useUiStore((s) => s.userMenuOpen);
  const toggleTheme = useUiStore((s) => s.toggleTheme);
  const setSettingsOpen = useUiStore((s) => s.setSettingsOpen);
  const setUserMenuOpen = useUiStore((s) => s.setUserMenuOpen);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100">
      <ModuleRail
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenSettings={() => setSettingsOpen(true)}
        onToggleUserMenu={() => setUserMenuOpen(!userMenuOpen)}
      />
      <main className="min-w-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
      {userMenuOpen && (
        <UserMenu user={user} onLogout={logout} onClose={() => setUserMenuOpen(false)} />
      )}
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
