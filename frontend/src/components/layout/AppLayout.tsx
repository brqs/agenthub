import { Outlet } from 'react-router-dom';
import { ModuleRail } from './ModuleRail';
import { SettingsDialog } from './SettingsDialog';
import { UserMenu } from './UserMenu';
import { OfflineBanner } from './OfflineBanner';
import { StreamSupervisor } from '@/components/chat/StreamSupervisor';
import { MobileBottomNav } from '@/components/mobile/MobileBottomNav';
import { useNetworkStatus } from '@/hooks/useNetworkStatus';
import { useStreamRecovery } from '@/hooks/useStreamRecovery';
import { useVisualViewportHeight } from '@/hooks/useVisualViewportHeight';
import { usePwaUpdate } from '@/lib/pwa';
import { resetClientSession } from '@/lib/session';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';
import { useUiStore } from '@/stores/uiStore';

export function AppLayout() {
  useVisualViewportHeight();
  useStreamRecovery();
  const isOnline = useNetworkStatus();
  const { updateAvailable, applyUpdate } = usePwaUpdate();
  const user = useAuthStore((s) => s.user);
  const selectedConversationId = useChatStore((s) => s.selectedConversationId);
  const activeStreams = useChatStore((s) => s.activeStreams);
  const themePreference = useUiStore((s) => s.themePreference);
  const resolvedTheme = useUiStore((s) => s.resolvedTheme);
  const settingsOpen = useUiStore((s) => s.settingsOpen);
  const userMenuOpen = useUiStore((s) => s.userMenuOpen);
  const cycleThemePreference = useUiStore((s) => s.cycleThemePreference);
  const setSettingsOpen = useUiStore((s) => s.setSettingsOpen);
  const setUserMenuOpen = useUiStore((s) => s.setUserMenuOpen);
  const setConversationSidebarCollapsed = useUiStore(
    (s) => s.setConversationSidebarCollapsed,
  );
  const activeStreamConversationId = Object.values(activeStreams)
    .sort((a, b) => Date.parse(b.startedAt) - Date.parse(a.startedAt))[0]?.conversationId;
  const chatHref = selectedConversationId
    ? `/chat/${selectedConversationId}`
    : activeStreamConversationId
      ? `/chat/${activeStreamConversationId}`
      : '/chat';

  return (
    <div className="app-viewport surface-app flex w-screen overflow-hidden">
      <ModuleRail
        themePreference={themePreference}
        resolvedTheme={resolvedTheme}
        onCycleTheme={cycleThemePreference}
        onOpenSettings={() => setSettingsOpen(true)}
        onToggleUserMenu={() => setUserMenuOpen(!userMenuOpen)}
        onChatClick={() => setConversationSidebarCollapsed(false)}
        chatHref={chatHref}
      />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <OfflineBanner
          isOnline={isOnline}
          updateAvailable={updateAvailable}
          onApplyUpdate={applyUpdate}
        />
        <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
        <MobileBottomNav
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenUserMenu={() => setUserMenuOpen(true)}
        />
      </div>
      {userMenuOpen && (
        <UserMenu
          user={user}
          onLogout={resetClientSession}
          onClose={() => setUserMenuOpen(false)}
        />
      )}
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <StreamSupervisor />
    </div>
  );
}
