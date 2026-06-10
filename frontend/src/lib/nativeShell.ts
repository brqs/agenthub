import { App } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import { Capacitor } from '@capacitor/core';
import { isDesktopRuntime, openDesktopExternalUrl } from '@/lib/desktopBridge';
import { useUiStore } from '@/stores/uiStore';

let initialized = false;

export type ShellPlatform = 'web' | 'capacitor' | 'tauri';

export function getShellPlatform(): ShellPlatform {
  if (Capacitor.isNativePlatform()) return 'capacitor';
  if (isDesktopRuntime()) return 'tauri';
  return 'web';
}

export function initializeShell(): void {
  if (initialized) return;
  const platform = getShellPlatform();
  if (platform === 'web') return;
  initialized = true;
  document.documentElement.classList.add('is-native-shell');
  document.documentElement.dataset.shellPlatform = platform;
  if (platform === 'tauri') return;
  void App.addListener('backButton', ({ canGoBack }) => {
    void handleNativeBackButton(canGoBack);
  });
}

export const initializeNativeShell = initializeShell;

export async function handleNativeBackButton(canGoBack: boolean): Promise<void> {
  if (closeTransientUi()) return;
  if (canGoBack) {
    window.history.back();
    return;
  }
  await App.exitApp();
}

export async function openExternalUrl(url: string): Promise<void> {
  const platform = getShellPlatform();
  if (platform === 'tauri') {
    await openDesktopExternalUrl(url);
    return;
  }
  if (platform === 'capacitor') {
    await Browser.open({ url });
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

export function handleExternalLink(
  event: React.MouseEvent<HTMLAnchorElement>,
  url: string | null | undefined,
): void {
  if (!url || getShellPlatform() === 'web') return;
  event.preventDefault();
  void openExternalUrl(url);
}

function closeTransientUi(): boolean {
  const state = useUiStore.getState();
  if (state.mobileSheet !== 'none') {
    state.closeMobileSheet();
    return true;
  }
  if (state.settingsOpen) {
    state.setSettingsOpen(false);
    return true;
  }
  if (state.userMenuOpen) {
    state.setUserMenuOpen(false);
    return true;
  }
  return false;
}
