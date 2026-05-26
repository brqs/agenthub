import { useUiStore } from './uiStore';

describe('uiStore', () => {
  beforeEach(() => {
    document.documentElement.className = '';
    useUiStore.setState({
      theme: 'dark',
      settingsOpen: false,
      userMenuOpen: false,
      rightPanelOpen: true,
      conversationSidebarCollapsed: false,
    });
    useUiStore.getState().setTheme('dark');
  });

  it('toggles theme and updates the document class', () => {
    useUiStore.getState().toggleTheme();

    expect(useUiStore.getState().theme).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    useUiStore.getState().toggleTheme();

    expect(useUiStore.getState().theme).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
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
});
