import { useSyncExternalStore } from 'react';
import { Capacitor } from '@capacitor/core';

const listeners = new Set<() => void>();
let updateAvailable = false;

export function registerPwa(): void {
  if (isDesktopRuntime()) {
    cleanupDesktopPwaState();
    return;
  }

  if (!import.meta.env.PROD || Capacitor.isNativePlatform() || !('serviceWorker' in navigator)) return;

  window.addEventListener(
    'load',
    () => {
      void navigator.serviceWorker.register('/sw.js').then(watchForUpdates).catch(() => undefined);
    },
    { once: true },
  );
}

function cleanupDesktopPwaState(): void {
  if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
    void navigator.serviceWorker
      .getRegistrations()
      .then((registrations) => Promise.all(registrations.map((item) => item.unregister())))
      .catch(() => undefined);
  }

  if (typeof window !== 'undefined' && 'caches' in window) {
    void window.caches
      .keys()
      .then((names) => Promise.all(names.map((name) => window.caches.delete(name))))
      .catch(() => undefined);
  }
}

function isDesktopRuntime(): boolean {
  if (typeof window === 'undefined') return false;
  const maybeTauri = window as Window & {
    __TAURI__?: unknown;
    __TAURI_INTERNALS__?: unknown;
  };
  return (
    Boolean(maybeTauri.__TAURI__ || maybeTauri.__TAURI_INTERNALS__) ||
    window.location.origin === 'http://tauri.localhost' ||
    window.location.origin === 'https://tauri.localhost'
  );
}

export function usePwaUpdate(): { updateAvailable: boolean; applyUpdate: () => void } {
  return {
    updateAvailable: useSyncExternalStore(subscribe, getSnapshot, getSnapshot),
    applyUpdate: () => window.location.reload(),
  };
}

function watchForUpdates(registration: ServiceWorkerRegistration): void {
  registration.addEventListener('updatefound', () => {
    const worker = registration.installing;
    if (!worker) return;
    worker.addEventListener('statechange', () => {
      if (worker.state !== 'installed' || !navigator.serviceWorker.controller) return;
      updateAvailable = true;
      listeners.forEach((listener) => listener());
    });
  });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): boolean {
  return updateAvailable;
}
