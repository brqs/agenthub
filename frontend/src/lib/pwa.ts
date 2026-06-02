import { useSyncExternalStore } from 'react';
import { Capacitor } from '@capacitor/core';

const listeners = new Set<() => void>();
let updateAvailable = false;

export function registerPwa(): void {
  if (!import.meta.env.PROD || Capacitor.isNativePlatform() || !('serviceWorker' in navigator)) return;

  window.addEventListener(
    'load',
    () => {
      void navigator.serviceWorker.register('/sw.js').then(watchForUpdates).catch(() => undefined);
    },
    { once: true },
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
