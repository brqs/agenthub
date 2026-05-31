/**
 * SSE client wrapping @microsoft/fetch-event-source (supports custom headers).
 *
 * Usage:
 *   const ctrl = subscribeMessageStream(messageId, {
 *     onEvent: (e) => { ... },
 *     onError: (err) => { ... },
 *   });
 *   // later:
 *   ctrl.abort();
 */

import { fetchEventSource, type EventSourceMessage } from '@microsoft/fetch-event-source';
import { env } from '@/lib/env';
import { useAuthStore } from '@/stores/authStore';
import type { StreamEvent } from './types';

export interface StreamSubscriber {
  onEvent: (ev: StreamEvent) => void;
  onError?: (err: unknown) => void;
  onClose?: () => void;
}

class FatalError extends Error {}

export function subscribeMessageStream(
  messageId: string,
  sub: StreamSubscriber,
): AbortController {
  const ctrl = new AbortController();
  const token = useAuthStore.getState().token;

  fetchEventSource(`${env.apiBaseUrl}/api/v1/messages/${messageId}/stream`, {
    method: 'GET',
    signal: ctrl.signal,
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    openWhenHidden: true,
    async onopen(response) {
      if (response.ok) return;
      if (response.status === 401 || response.status === 403) {
        throw new FatalError(`SSE auth failed: ${response.status}`);
      }
      // 其他错误：抛出以触发重连
      throw new Error(`SSE open failed: ${response.status}`);
    },
    onmessage(msg: EventSourceMessage) {
      try {
        const data = msg.data ? JSON.parse(msg.data) : {};
        sub.onEvent({ event: msg.event as StreamEvent['event'], data } as StreamEvent);
      } catch (e) {
        sub.onError?.(e);
      }
    },
    onerror(err) {
      if (err instanceof FatalError) {
        sub.onError?.(err);
        throw err; // 阻止重连
      }
      // 非致命错误：返回 undefined 让库自动重试
    },
    onclose() {
      sub.onClose?.();
    },
  }).catch((err) => sub.onError?.(err));

  return ctrl;
}
