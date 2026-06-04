/**
 * Centralized environment configuration.
 *
 * Pages and components MUST NOT read import.meta.env directly. The frontend
 * always uses the real backend; this module only centralizes its base URL.
 */

import { Capacitor } from '@capacitor/core';

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
const allowInsecureNativeApi =
  (import.meta.env.VITE_ALLOW_INSECURE_NATIVE_API as string | undefined) === 'true';

if (
  Capacitor.isNativePlatform() &&
  !apiBaseUrl.startsWith('https://') &&
  !(allowInsecureNativeApi && apiBaseUrl.startsWith('http://'))
) {
  throw new Error(
    'Capacitor runtime requires VITE_API_BASE_URL=https://... unless VITE_ALLOW_INSECURE_NATIVE_API=true is set for a temporary HTTP backend.',
  );
}

export const env = {
  /** Backend base URL. Empty string => use the Vite dev proxy (`/api/...`). */
  apiBaseUrl,
};
