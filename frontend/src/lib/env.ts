/**
 * Centralized environment configuration.
 *
 * Pages and components MUST NOT read import.meta.env directly. The frontend
 * always uses the real backend; this module only centralizes its base URL.
 */

import { Capacitor } from '@capacitor/core';
import {
  getStoredDesktopBackendUrl,
  isDesktopRuntime,
  normalizeBackendUrl,
  setStoredDesktopBackendUrl,
} from '@/lib/desktopBridge';

const configuredApiBaseUrl = normalizeOptionalApiBaseUrl(
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '',
);
const allowInsecureNativeApi =
  (import.meta.env.VITE_ALLOW_INSECURE_NATIVE_API as string | undefined) === 'true';
const allowInsecureDesktopApi =
  (import.meta.env.VITE_ALLOW_INSECURE_DESKTOP_API as string | undefined) === 'true';
const apiBaseUrlSubscribers = new Set<(url: string) => void>();

let runtimeApiBaseUrl = initialApiBaseUrl();

if (
  Capacitor.isNativePlatform() &&
  !isDesktopRuntime() &&
  !configuredApiBaseUrl.startsWith('https://') &&
  !(allowInsecureNativeApi && configuredApiBaseUrl.startsWith('http://'))
) {
  throw new Error(
    'Capacitor runtime requires VITE_API_BASE_URL=https://... unless VITE_ALLOW_INSECURE_NATIVE_API=true is set for a temporary HTTP backend.',
  );
}

if (isDesktopRuntime() && configuredApiBaseUrl && !isAllowedDesktopApiUrl(configuredApiBaseUrl)) {
  throw new Error(
    'Tauri desktop runtime requires HTTPS for remote backends. Localhost HTTP is allowed; set VITE_ALLOW_INSECURE_DESKTOP_API=true only for a trusted development backend.',
  );
}

export const env = {
  /** Backend base URL. Empty string => use the Vite dev proxy (`/api/...`). */
  get apiBaseUrl() {
    return runtimeApiBaseUrl;
  },
};

export function getApiBaseUrl(): string {
  return runtimeApiBaseUrl;
}

export function setRuntimeApiBaseUrl(
  url: string,
  options: { persistDesktop?: boolean } = {},
): string {
  const normalized = normalizeOptionalApiBaseUrl(url);
  if (isDesktopRuntime() && normalized && !isAllowedDesktopApiUrl(normalized)) {
    throw new Error('桌面客户端连接远程后端时必须使用 HTTPS。');
  }
  runtimeApiBaseUrl = normalized;
  if (options.persistDesktop && isDesktopRuntime() && normalized) {
    setStoredDesktopBackendUrl(normalized);
  }
  for (const subscriber of apiBaseUrlSubscribers) {
    subscriber(normalized);
  }
  return normalized;
}

export function subscribeApiBaseUrl(listener: (url: string) => void): () => void {
  apiBaseUrlSubscribers.add(listener);
  return () => {
    apiBaseUrlSubscribers.delete(listener);
  };
}

function initialApiBaseUrl(): string {
  if (configuredApiBaseUrl) return configuredApiBaseUrl;
  if (isDesktopRuntime()) return getStoredDesktopBackendUrl();
  return '';
}

function normalizeOptionalApiBaseUrl(url: string): string {
  const raw = url.trim();
  if (!raw) return '';
  return normalizeBackendUrl(raw);
}

function isAllowedDesktopApiUrl(url: string): boolean {
  if (url.startsWith('https://')) return true;
  if (!url.startsWith('http://')) return false;
  if (allowInsecureDesktopApi) return true;
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host === 'localhost' || host === '127.0.0.1' || host === '::1';
  } catch {
    return false;
  }
}
