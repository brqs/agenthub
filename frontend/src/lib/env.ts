/**
 * Centralized environment configuration.
 *
 * Pages and components MUST NOT read import.meta.env directly. The frontend
 * always uses the real backend; this module only centralizes its base URL.
 */

export const env = {
  /** Backend base URL. Empty string => use the Vite dev proxy (`/api/...`). */
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '',
};
