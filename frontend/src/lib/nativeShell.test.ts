import { App } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import { Capacitor } from '@capacitor/core';
import { openDesktopExternalUrl } from './desktopBridge';
import { getShellPlatform, handleNativeBackButton, openExternalUrl } from './nativeShell';
import { useUiStore } from '@/stores/uiStore';

vi.mock('@capacitor/app', () => ({
  App: {
    addListener: vi.fn(),
    exitApp: vi.fn(),
  },
}));

vi.mock('@capacitor/browser', () => ({
  Browser: {
    open: vi.fn(),
  },
}));

vi.mock('@capacitor/core', () => ({
  Capacitor: {
    isNativePlatform: vi.fn(),
  },
}));

vi.mock('./desktopBridge', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./desktopBridge')>();
  return {
    ...actual,
    openDesktopExternalUrl: vi.fn(),
  };
});

describe('nativeShell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete window.__TAURI_INTERNALS__;
    useUiStore.setState({
      mobileSheet: 'none',
      settingsOpen: false,
      userMenuOpen: false,
    });
    vi.mocked(Capacitor.isNativePlatform).mockReturnValue(true);
    vi.mocked(App.exitApp).mockResolvedValue();
    vi.mocked(Browser.open).mockResolvedValue();
    vi.mocked(openDesktopExternalUrl).mockResolvedValue({ opened: true });
  });

  it('closes a mobile sheet before navigating back', async () => {
    useUiStore.getState().openMobileSheet('workspace');

    await handleNativeBackButton(false);

    expect(useUiStore.getState().mobileSheet).toBe('none');
    expect(App.exitApp).not.toHaveBeenCalled();
  });

  it('exits the Android app when no back navigation remains', async () => {
    await handleNativeBackButton(false);

    expect(App.exitApp).toHaveBeenCalledOnce();
  });

  it('uses the native browser for external URLs', async () => {
    await openExternalUrl('https://example.com');

    expect(Browser.open).toHaveBeenCalledWith({ url: 'https://example.com' });
  });

  it('detects the Tauri desktop shell and opens external URLs through the validated bridge', async () => {
    vi.mocked(Capacitor.isNativePlatform).mockReturnValue(false);
    window.__TAURI_INTERNALS__ = {};

    expect(getShellPlatform()).toBe('tauri');

    await openExternalUrl('https://example.com');

    expect(openDesktopExternalUrl).toHaveBeenCalledWith('https://example.com');
    expect(Browser.open).not.toHaveBeenCalled();
  });
});
