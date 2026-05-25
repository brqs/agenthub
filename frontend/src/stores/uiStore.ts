import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemeMode = 'dark' | 'light';

interface UiState {
  theme: ThemeMode;
  settingsOpen: boolean;
  userMenuOpen: boolean;
  rightPanelOpen: boolean;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
  setSettingsOpen: (open: boolean) => void;
  setUserMenuOpen: (open: boolean) => void;
  setRightPanelOpen: (open: boolean) => void;
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
    }),
    {
      name: 'agenthub-ui',
      partialize: (state) => ({ theme: state.theme, rightPanelOpen: state.rightPanelOpen }),
      onRehydrateStorage: () => (state) => {
        applyTheme(state?.theme ?? 'dark');
      },
    },
  ),
);

applyTheme(useUiStore.getState().theme);
