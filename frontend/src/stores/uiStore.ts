import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemeMode = 'dark' | 'light';

interface UiState {
  theme: ThemeMode;
  settingsOpen: boolean;
  userMenuOpen: boolean;
  rightPanelOpen: boolean;
  conversationSidebarCollapsed: boolean;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
  setSettingsOpen: (open: boolean) => void;
  setUserMenuOpen: (open: boolean) => void;
  setRightPanelOpen: (open: boolean) => void;
  setConversationSidebarCollapsed: (collapsed: boolean) => void;
  toggleConversationSidebar: () => void;
}

function applyTheme(theme: ThemeMode) {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.documentElement.style.colorScheme = theme;
}

export const useUiStore = create<UiState>()(
  persist(
    (set, get) => ({
      theme: 'dark',
      settingsOpen: false,
      userMenuOpen: false,
      rightPanelOpen: true,
      conversationSidebarCollapsed: false,
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },
      toggleTheme: () => {
        const nextTheme = get().theme === 'dark' ? 'light' : 'dark';
        applyTheme(nextTheme);
        set({ theme: nextTheme });
      },
      setSettingsOpen: (open) => set({ settingsOpen: open }),
      setUserMenuOpen: (open) => set({ userMenuOpen: open }),
      setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
      setConversationSidebarCollapsed: (collapsed) => set({ conversationSidebarCollapsed: collapsed }),
      toggleConversationSidebar: () =>
        set((state) => ({ conversationSidebarCollapsed: !state.conversationSidebarCollapsed })),
    }),
    {
      name: 'agenthub-ui',
      partialize: (state) => ({
        theme: state.theme,
        rightPanelOpen: state.rightPanelOpen,
        conversationSidebarCollapsed: state.conversationSidebarCollapsed,
      }),
      onRehydrateStorage: () => (state) => {
        applyTheme(state?.theme ?? 'dark');
      },
    },
  ),
);

applyTheme(useUiStore.getState().theme);
