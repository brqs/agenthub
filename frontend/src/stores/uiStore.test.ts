import { useUiStore } from './uiStore';

describe('uiStore', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    document.documentElement.className = '';
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.removeAttribute('data-theme-preference');
    useUiStore.setState({
      theme: 'dark',
      themePreference: 'dark',
      resolvedTheme: 'dark',
      systemTheme: 'unknown',
      settingsOpen: false,
      userMenuOpen: false,
      rightPanelOpen: true,
      rightPanelWidth: 380,
      conversationSidebarCollapsed: false,
    });
    useUiStore.getState().setTheme('dark');
  });

  it('keeps setTheme as a dark/light compatibility action', () => {
    useUiStore.getState().setTheme('light');

    expect(useUiStore.getState().themePreference).toBe('light');
    expect(useUiStore.getState().resolvedTheme).toBe('light');
    expect(useUiStore.getState().theme).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(document.documentElement.dataset.theme).toBe('light');

    useUiStore.getState().setTheme('dark');

    expect(useUiStore.getState().themePreference).toBe('dark');
    expect(useUiStore.getState().resolvedTheme).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.dataset.themePreference).toBe('dark');
  });

  it('cycles theme preference through light, system, and dark', () => {
    useUiStore.getState().toggleTheme();

    expect(useUiStore.getState().themePreference).toBe('light');
    expect(useUiStore.getState().theme).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    useUiStore.getState().toggleTheme();

    expect(useUiStore.getState().themePreference).toBe('system');
    expect(useUiStore.getState().theme).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('resolves system preference from matchMedia', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));

    useUiStore.getState().setThemePreference('system');

    expect(useUiStore.getState().themePreference).toBe('system');
    expect(useUiStore.getState().systemTheme).toBe('light');
    expect(useUiStore.getState().resolvedTheme).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(document.documentElement.dataset.themePreference).toBe('system');
  });

  it('tracks settings and user menu visibility', () => {
    useUiStore.getState().setSettingsOpen(true);
    useUiStore.getState().setUserMenuOpen(true);

    expect(useUiStore.getState().settingsOpen).toBe(true);
    expect(useUiStore.getState().userMenuOpen).toBe(true);
  });

  it('tracks conversation sidebar collapsed state', () => {
    useUiStore.getState().setConversationSidebarCollapsed(true);

    expect(useUiStore.getState().conversationSidebarCollapsed).toBe(true);

    useUiStore.getState().toggleConversationSidebar();

    expect(useUiStore.getState().conversationSidebarCollapsed).toBe(false);
  });

  it('clamps right panel width', () => {
    useUiStore.getState().setRightPanelWidth(900);
    expect(useUiStore.getState().rightPanelWidth).toBe(560);

    useUiStore.getState().setRightPanelWidth(100);
    expect(useUiStore.getState().rightPanelWidth).toBe(320);

    useUiStore.getState().setRightPanelWidth(421);
    expect(useUiStore.getState().rightPanelWidth).toBe(421);
  });
});
