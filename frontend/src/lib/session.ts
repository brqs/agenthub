import { env } from '@/lib/env';
import { queryClient } from '@/lib/queryClient';
import type { User } from '@/lib/types';
import { useAgentStore } from '@/stores/agentStore';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

export function clearSessionData() {
  queryClient.clear();

  if (env.useMockApi) {
    useAgentStore.getState().resetAgents();
    useChatStore.getState().resetChat();
  } else {
    useAgentStore.getState().clearAgents();
    useChatStore.getState().clearChat();
  }
}

export function resetClientSession() {
  clearSessionData();
  useAuthStore.getState().logout();
}

export function startClientSession(token: string, user: User) {
  clearSessionData();
  useAuthStore.getState().setAuth(token, user);
}
