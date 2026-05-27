import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemeMode = 'dark' | 'light';

export const RIGHT_PANEL_MIN_WIDTH = 320;
export const RIGHT_PANEL_DEFAULT_WIDTH = 380;
export const RIGHT_PANEL_MAX_WIDTH = 560;

interface UiState {
  theme: ThemeMode;
  settingsOpen: boolean;
  userMenuOpen: boolean;
  rightPanelOpen: boolean;
  rightPanelWidth: number;
  conversationSidebarCollapsed: boolean;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
  setSettingsOpen: (open: boolean) => void;
  setUserMenuOpen: (open: boolean) => void;
  setRightPanelOpen: (open: boolean) => void;
  setRightPanelWidth: (width: number) => void;
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
      rightPanelWidth: RIGHT_PANEL_DEFAULT_WIDTH,
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
      setRightPanelWidth: (width) =>
        set({
          rightPanelWidth: Math.min(
            RIGHT_PANEL_MAX_WIDTH,
            Math.max(RIGHT_PANEL_MIN_WIDTH, Math.round(width)),
          ),
        }),
      setConversationSidebarCollapsed: (collapsed) => set({ conversationSidebarCollapsed: collapsed }),
      toggleConversationSidebar: () =>
        set((state) => ({ conversationSidebarCollapsed: !state.conversationSidebarCollapsed })),
    }),
    {
      name: 'agenthub-ui',
      partialize: (state) => ({
        theme: state.theme,
        rightPanelOpen: state.rightPanelOpen,
        rightPanelWidth: state.rightPanelWidth,
        conversationSidebarCollapsed: state.conversationSidebarCollapsed,
      }),
      onRehydrateStorage: () => (state) => {
        applyTheme(state?.theme ?? 'dark');
      },
    },
  ),
);

applyTheme(useUiStore.getState().theme);
