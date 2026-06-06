import { App } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import { Capacitor } from '@capacitor/core';
import { useUiStore } from '@/stores/uiStore';

let initialized = false;

export function initializeNativeShell(): void {
  if (!Capacitor.isNativePlatform() || initialized) return;
  initialized = true;
  document.documentElement.classList.add('is-native-shell');
  void App.addListener('backButton', ({ canGoBack }) => {
    void handleNativeBackButton(canGoBack);
  });
}

export async function handleNativeBackButton(canGoBack: boolean): Promise<void> {
  if (closeTransientUi()) return;
  if (canGoBack) {
    window.history.back();
    return;
  }
  await App.exitApp();
}

export async function openExternalUrl(url: string): Promise<void> {
  if (Capacitor.isNativePlatform()) {
    await Browser.open({ url });
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

export function handleExternalLink(
  event: React.MouseEvent<HTMLAnchorElement>,
  url: string | null | undefined,
): void {
  if (!url || !Capacitor.isNativePlatform()) return;
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
