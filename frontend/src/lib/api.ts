/**
 * REST API client with JWT interceptor.
 *
 * Usage:
 *   import { api } from '@/lib/api';
 *   const convs = await api.get<ConversationList>('/api/v1/conversations');
 */

import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';
import { getApiBaseUrl, subscribeApiBaseUrl } from '@/lib/env';
import { resetClientSession } from '@/lib/session';
import { useAuthStore } from '@/stores/authStore';

export const api: AxiosInstance = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

type RetriableRequestConfig = InternalAxiosRequestConfig & { _authRetry?: boolean };
type RefreshResponse = {
  access_token: string;
  refresh_token?: string | null;
  expires_in?: number | null;
  user: import('@/lib/types').User;
  session?: { id?: string } | null;
};

let refreshPromise: Promise<RefreshResponse> | null = null;

subscribeApiBaseUrl((url) => {
  api.defaults.baseURL = url;
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (resp) => resp,
  async (err: AxiosError<{ error?: { code?: string; message?: string } }>) => {
    const original = err.config as RetriableRequestConfig | undefined;
    if (err.response?.status === 401 && original && !original._authRetry) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        original._authRetry = true;
        original.headers.Authorization = `Bearer ${refreshed.access_token}`;
        return api.request(original);
      }
      resetClientSession();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  },
);

async function refreshAccessToken(): Promise<RefreshResponse | null> {
  const state = useAuthStore.getState();
  if (!state.refreshToken) return null;
  refreshPromise ??= axios
    .post<RefreshResponse>(`${getApiBaseUrl()}/api/v1/auth/refresh`, {
      refresh_token: state.refreshToken,
    })
    .then((response) => response.data)
    .finally(() => {
      refreshPromise = null;
    });
  try {
    const refreshed = await refreshPromise;
    useAuthStore.getState().setAuth(refreshed.access_token, refreshed.user, {
      refreshToken: refreshed.refresh_token ?? state.refreshToken,
      sessionId: refreshed.session?.id ?? state.sessionId,
      expiresIn: refreshed.expires_in ?? state.expiresIn,
    });
    return refreshed;
  } catch {
    return null;
  }
}

export function extractApiError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as
      | {
          error?: { code?: string; message?: string };
          detail?: { error?: { code?: string; message?: string } };
        }
      | undefined;
    const error = data?.detail?.error ?? data?.error;
    if (error?.code === 'CONVERSATION_BUSY') {
      return '上一条回复仍未结束，请稍后再发，或重试/刷新该回复。';
    }
    return error?.message || err.message;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
