import { queryClient } from '@/lib/queryClient';
import { setRuntimeApiBaseUrl } from '@/lib/env';
import type { User } from '@/lib/types';
import { useAgentStore } from '@/stores/agentStore';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

export function clearSessionData() {
  queryClient.clear();

  useAgentStore.getState().clearAgents();
  useChatStore.getState().clearChat();
}

export function resetClientSession() {
  clearSessionData();
  useAuthStore.getState().logout();
}

export function startClientSession(
  token: string,
  user: User,
  options: { refreshToken?: string | null; sessionId?: string | null; expiresIn?: number | null } = {},
) {
  clearSessionData();
  useAuthStore.getState().setAuth(token, user, options);
}

export function switchClientBackend(url: string, persistDesktop = false) {
  clearSessionData();
  setRuntimeApiBaseUrl(url, { persistDesktop });
  useAuthStore.getState().activateBackend(url);
}
