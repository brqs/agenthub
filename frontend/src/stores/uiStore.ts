import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemeMode = 'dark' | 'light';
export type ThemePreference = 'system' | ThemeMode;
export type SystemTheme = ThemeMode | 'unknown';
export type MobileSheet = 'none' | 'conversation-list' | 'workspace';

export const RIGHT_PANEL_MIN_WIDTH = 320;
export const RIGHT_PANEL_DEFAULT_WIDTH = 380;
export const RIGHT_PANEL_MAX_WIDTH = 560;

interface UiState {
  theme: ThemeMode;
  themePreference: ThemePreference;
  resolvedTheme: ThemeMode;
  systemTheme: SystemTheme;
  settingsOpen: boolean;
  userMenuOpen: boolean;
  rightPanelOpen: boolean;
  rightPanelWidth: number;
  conversationSidebarCollapsed: boolean;
  mobileSheet: MobileSheet;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
  setThemePreference: (preference: ThemePreference) => void;
  cycleThemePreference: () => void;
  setSettingsOpen: (open: boolean) => void;
  setUserMenuOpen: (open: boolean) => void;
  setRightPanelOpen: (open: boolean) => void;
  setRightPanelWidth: (width: number) => void;
  setConversationSidebarCollapsed: (collapsed: boolean) => void;
  toggleConversationSidebar: () => void;
  openMobileSheet: (sheet: Exclude<MobileSheet, 'none'>) => void;
  closeMobileSheet: () => void;
}

const THEME_CYCLE: ThemePreference[] = ['system', 'dark', 'light'];

function getSystemTheme(): SystemTheme {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return 'unknown';
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function normalizeThemePreference(value: unknown): ThemePreference {
  return value === 'system' || value === 'dark' || value === 'light' ? value : 'system';
}

function resolveTheme(preference: ThemePreference, systemTheme = getSystemTheme()): ThemeMode {
  if (preference !== 'system') return preference;
  return systemTheme === 'light' ? 'light' : 'dark';
}

function applyTheme(preference: ThemePreference, resolvedTheme: ThemeMode) {
  document.documentElement.classList.toggle('dark', resolvedTheme === 'dark');
  document.documentElement.dataset.theme = resolvedTheme;
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.style.colorScheme = resolvedTheme;
}

function applyPreference(preference: ThemePreference) {
  const systemTheme = getSystemTheme();
  const resolvedTheme = resolveTheme(preference, systemTheme);
  applyTheme(preference, resolvedTheme);
  return {
    theme: resolvedTheme,
    themePreference: preference,
    resolvedTheme,
    systemTheme,
  };
}

const initialTheme = applyPreference('system');

export const useUiStore = create<UiState>()(
  persist(
    (set, get) => ({
      ...initialTheme,
      settingsOpen: false,
      userMenuOpen: false,
      rightPanelOpen: true,
      rightPanelWidth: RIGHT_PANEL_DEFAULT_WIDTH,
      conversationSidebarCollapsed: false,
      mobileSheet: 'none',
      setTheme: (theme) => {
        set(applyPreference(theme));
      },
      toggleTheme: () => {
        get().cycleThemePreference();
      },
      setThemePreference: (preference) => {
        set(applyPreference(preference));
      },
      cycleThemePreference: () => {
        const currentIndex = THEME_CYCLE.indexOf(get().themePreference);
        const nextPreference = THEME_CYCLE[(currentIndex + 1) % THEME_CYCLE.length] ?? 'system';
        set(applyPreference(nextPreference));
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
      openMobileSheet: (sheet) => set({ mobileSheet: sheet }),
      closeMobileSheet: () => set({ mobileSheet: 'none' }),
    }),
    {
      name: 'agenthub-ui',
      version: 2,
      migrate: (persisted) => {
        const value = persisted as Partial<UiState> | undefined;
        const themePreference = normalizeThemePreference(value?.themePreference ?? value?.theme);
        return {
          themePreference,
          rightPanelOpen: value?.rightPanelOpen ?? true,
          rightPanelWidth: value?.rightPanelWidth ?? RIGHT_PANEL_DEFAULT_WIDTH,
          conversationSidebarCollapsed: value?.conversationSidebarCollapsed ?? false,
        };
      },
      merge: (persisted, current) => {
        const value = persisted as Partial<UiState> | undefined;
        const themePreference = normalizeThemePreference(value?.themePreference ?? value?.theme);
        return {
          ...current,
          ...value,
          ...applyPreference(themePreference),
        };
      },
      partialize: (state) => ({
        themePreference: state.themePreference,
        rightPanelOpen: state.rightPanelOpen,
        rightPanelWidth: state.rightPanelWidth,
        conversationSidebarCollapsed: state.conversationSidebarCollapsed,
      }),
      onRehydrateStorage: () => (state) => {
        const themePreference = normalizeThemePreference(state?.themePreference ?? state?.theme);
        const nextTheme = applyPreference(themePreference);
        applyTheme(nextTheme.themePreference, nextTheme.resolvedTheme);
      },
    },
  ),
);

if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const updateSystemTheme = () => {
    const state = useUiStore.getState();
    if (state.themePreference !== 'system') {
      useUiStore.setState({ systemTheme: getSystemTheme() });
      return;
    }
    useUiStore.setState(applyPreference('system'));
  };
  if (typeof media.addEventListener === 'function') {
    media.addEventListener('change', updateSystemTheme);
  } else {
    media.addListener(updateSystemTheme);
  }
}

const currentTheme = useUiStore.getState();
applyTheme(currentTheme.themePreference, currentTheme.resolvedTheme);
