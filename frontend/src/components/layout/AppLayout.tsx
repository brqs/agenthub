import { Outlet } from 'react-router-dom';
import { ModuleRail } from './ModuleRail';
import { SettingsDialog } from './SettingsDialog';
import { UserMenu } from './UserMenu';
import { resetClientSession } from '@/lib/session';
import { useAuthStore } from '@/stores/authStore';
import { useUiStore } from '@/stores/uiStore';

export function AppLayout() {
  const user = useAuthStore((s) => s.user);
  const themePreference = useUiStore((s) => s.themePreference);
  const resolvedTheme = useUiStore((s) => s.resolvedTheme);
  const settingsOpen = useUiStore((s) => s.settingsOpen);
  const userMenuOpen = useUiStore((s) => s.userMenuOpen);
  const cycleThemePreference = useUiStore((s) => s.cycleThemePreference);
  const setSettingsOpen = useUiStore((s) => s.setSettingsOpen);
  const setUserMenuOpen = useUiStore((s) => s.setUserMenuOpen);

  return (
    <div className="surface-app flex h-screen w-screen overflow-hidden">
      <ModuleRail
        themePreference={themePreference}
        resolvedTheme={resolvedTheme}
        onCycleTheme={cycleThemePreference}
        onOpenSettings={() => setSettingsOpen(true)}
        onToggleUserMenu={() => setUserMenuOpen(!userMenuOpen)}
      />
      <main className="min-w-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
      {userMenuOpen && (
        <UserMenu
          user={user}
          onLogout={resetClientSession}
          onClose={() => setUserMenuOpen(false)}
        />
      )}
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
