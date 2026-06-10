import { useEffect } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { getApiBaseUrl } from '@/lib/env';
import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { useAuthStore } from '@/stores/authStore';

interface UserEvent {
  cursor: number;
  event_type: string;
  resource_type: string;
  resource_id: string;
  conversation_id?: string | null;
}

export function useRealtimeEvents() {
  const token = useAuthStore((state) => state.token);
  const userId = useAuthStore((state) => state.user?.id);
  const backendKey = useAuthStore((state) => state.backendKey);

  useEffect(() => {
    if (!token || !userId) return;
    const controller = new AbortController();
    const cursorKey = `agenthub-events:${backendKey}:${userId}`;
    const cursor = readStoredCursor(cursorKey);
    const query = cursor > 0 ? `?cursor=${cursor}` : '';
    void fetchEventSource(`${getApiBaseUrl()}/api/v1/events/stream${query}`, {
      signal: controller.signal,
      headers: { Authorization: `Bearer ${token}` },
      onmessage(event) {
        if (!event.data) return;
        try {
          const parsed = JSON.parse(event.data) as UserEvent;
          if (parsed.cursor) {
            window.localStorage.setItem(cursorKey, String(parsed.cursor));
          }
          invalidateForEvent(parsed, userId);
        } catch {
          // Ignore malformed realtime events; REST hydration remains the source of truth.
        }
      },
    }).catch(() => {
      // Network loss is expected on laptop sleep/backend restarts. The next mount reconnects.
    });
    return () => controller.abort();
  }, [backendKey, token, userId]);
}

function readStoredCursor(key: string): number {
  if (typeof window === 'undefined') return 0;
  const parsed = Number(window.localStorage.getItem(key) || '0');
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function invalidateForEvent(event: UserEvent, userId: string): void {
  if (event.resource_type === 'conversation') {
    void queryClient.invalidateQueries({ queryKey: queryKeys.conversations(userId) });
  }
  if (event.conversation_id) {
    void queryClient.invalidateQueries({
      queryKey: queryKeys.messages(userId, event.conversation_id),
    });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.workspaceArtifacts(userId, event.conversation_id),
    });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.orchestratorRuns(userId, event.conversation_id),
    });
  }
  if (event.resource_type === 'agent') {
    void queryClient.invalidateQueries({ queryKey: queryKeys.agents(userId) });
  }
}
