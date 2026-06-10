import { create } from 'zustand';
import { getApiBaseUrl } from '@/lib/env';
import type { User } from '@/lib/types';

const LEGACY_AUTH_STORAGE_KEY = 'agenthub-auth';
const AUTH_STORAGE_PREFIX = 'agenthub-auth:';

interface StoredAuthState {
  token: string | null;
  refreshToken: string | null;
  sessionId: string | null;
  expiresIn: number | null;
  user: User | null;
}

interface AuthState extends StoredAuthState {
  backendKey: string;
  setAuth: (
    token: string,
    user: User,
    options?: { refreshToken?: string | null; sessionId?: string | null; expiresIn?: number | null },
  ) => void;
  setUser: (user: User) => void;
  activateBackend: (url: string) => void;
  logout: () => void;
}

const initialBackendKey = backendStorageKey(getApiBaseUrl());
const initialAuth = loadAuthState(initialBackendKey);

export const useAuthStore = create<AuthState>((set, get) => ({
  ...initialAuth,
  backendKey: initialBackendKey,
  setAuth: (token, user, options = {}) => {
    const next = {
      token,
      user,
      refreshToken: options.refreshToken ?? get().refreshToken,
      sessionId: options.sessionId ?? get().sessionId,
      expiresIn: options.expiresIn ?? get().expiresIn,
    };
    saveAuthState(get().backendKey, next);
    set(next);
  },
  setUser: (user) => {
    const next = {
      token: get().token,
      refreshToken: get().refreshToken,
      sessionId: get().sessionId,
      expiresIn: get().expiresIn,
      user,
    };
    saveAuthState(get().backendKey, next);
    set({ user });
  },
  activateBackend: (url) => {
    const backendKey = backendStorageKey(url);
    set({ ...loadAuthState(backendKey), backendKey });
  },
  logout: () => {
    removeAuthState(get().backendKey);
    set({ token: null, refreshToken: null, sessionId: null, expiresIn: null, user: null });
  },
}));

export function backendStorageKey(url: string): string {
  const normalized = url.trim().replace(/\/+$/, '') || 'web-default';
  return `${AUTH_STORAGE_PREFIX}${encodeURIComponent(normalized)}`;
}

function loadAuthState(key: string): StoredAuthState {
  if (typeof window === 'undefined') return emptyAuthState();
  const scoped = parseStoredAuth(window.localStorage.getItem(key));
  if (scoped) return scoped;

  const legacy = parseStoredAuth(window.localStorage.getItem(LEGACY_AUTH_STORAGE_KEY));
  if (!legacy) return emptyAuthState();
  saveAuthState(key, legacy);
  window.localStorage.removeItem(LEGACY_AUTH_STORAGE_KEY);
  return legacy;
}

function parseStoredAuth(raw: string | null): StoredAuthState | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as {
      token?: unknown;
      refreshToken?: unknown;
      refresh_token?: unknown;
      sessionId?: unknown;
      session_id?: unknown;
      expiresIn?: unknown;
      expires_in?: unknown;
      user?: unknown;
      state?: {
        token?: unknown;
        refreshToken?: unknown;
        refresh_token?: unknown;
        sessionId?: unknown;
        session_id?: unknown;
        expiresIn?: unknown;
        expires_in?: unknown;
        user?: unknown;
      };
    };
    const source = parsed.state ?? parsed;
    return {
      token: typeof source.token === 'string' ? source.token : null,
      refreshToken:
        typeof source.refreshToken === 'string'
          ? source.refreshToken
          : typeof source.refresh_token === 'string'
            ? source.refresh_token
            : null,
      sessionId:
        typeof source.sessionId === 'string'
          ? source.sessionId
          : typeof source.session_id === 'string'
            ? source.session_id
            : null,
      expiresIn:
        typeof source.expiresIn === 'number'
          ? source.expiresIn
          : typeof source.expires_in === 'number'
            ? source.expires_in
            : null,
      user:
        source.user && typeof source.user === 'object'
          ? (source.user as User)
          : null,
    };
  } catch {
    return null;
  }
}

function emptyAuthState(): StoredAuthState {
  return {
    token: null,
    refreshToken: null,
    sessionId: null,
    expiresIn: null,
    user: null,
  };
}

function saveAuthState(key: string, state: StoredAuthState): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, JSON.stringify(state));
  } catch {
    // The in-memory session remains usable when persistent storage is unavailable.
  }
}

function removeAuthState(key: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Clearing in-memory auth is still sufficient for the current session.
  }
}
