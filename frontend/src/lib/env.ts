/**
 * Centralized environment configuration.
 *
 * Pages and components MUST NOT read import.meta.env directly — go through
 * adapters/hooks instead. Adapters read these flags to pick mock vs real API.
 *
 * Defaults are Mock-first so the local Demo works without any .env file.
 * Override via .env.local or shell env vars (see .env.example).
 */

function readFlag(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined) return fallback;
  return value !== 'false' && value !== '0';
}

export const env = {
  /** Backend base URL. Empty string => use the Vite dev proxy (`/api/...`). */
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '',

  /** When true, hooks/adapters return Mock data instead of calling the backend. */
  useMockApi: readFlag(import.meta.env.VITE_USE_MOCK_API as string | undefined, true),

  /** When true, SSE subscriptions are synthesized locally. Defaults to `useMockApi`. */
  useMockSse: readFlag(
    import.meta.env.VITE_USE_MOCK_SSE as string | undefined,
    readFlag(import.meta.env.VITE_USE_MOCK_API as string | undefined, true),
  ),
};
