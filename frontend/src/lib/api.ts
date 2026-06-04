/**
 * REST API client with JWT interceptor.
 *
 * Usage:
 *   import { api } from '@/lib/api';
 *   const convs = await api.get<ConversationList>('/api/v1/conversations');
 */

import axios, { AxiosError, type AxiosInstance } from 'axios';
import { resetClientSession } from '@/lib/session';
import { useAuthStore } from '@/stores/authStore';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
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
  (err: AxiosError<{ error?: { code?: string; message?: string } }>) => {
    if (err.response?.status === 401) {
      resetClientSession();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  },
);

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
