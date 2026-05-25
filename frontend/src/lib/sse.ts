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
import { useAuthStore } from '@/stores/authStore';
import type { StreamEvent } from './types';

export interface StreamSubscriber {
  onEvent: (ev: StreamEvent) => void;
  onError?: (err: unknown) => void;
  onClose?: () => void;
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false';

class FatalError extends Error {}

const MOCK_REPLY =
  '收到。我会沿用真实 SSE 事件格式来模拟后端：start、block_start、delta、block_end、done 都会经过同一个 useStream 管线。';

function subscribeMockMessageStream(sub: StreamSubscriber): AbortController {
  const ctrl = new AbortController();
  const events: StreamEvent[] = [
    { event: 'start', data: {} },
    { event: 'block_start', data: { block_index: 0, block_type: 'text' } },
    ...Array.from({ length: Math.ceil(MOCK_REPLY.length / 2) }, (_, index) => ({
      event: 'delta' as const,
      data: {
        block_index: 0,
        text_delta: MOCK_REPLY.slice(index * 2, index * 2 + 2),
      },
    })),
    { event: 'block_end', data: { block_index: 0 } },
    { event: 'done', data: { total_blocks: 1 } },
  ];

  let index = 0;
  const timer = window.setInterval(() => {
    if (ctrl.signal.aborted) {
      window.clearInterval(timer);
      return;
    }
    const event = events[index];
    if (!event) {
      window.clearInterval(timer);
      sub.onClose?.();
      return;
    }
    sub.onEvent(event);
    index += 1;
  }, 35);

  ctrl.signal.addEventListener('abort', () => {
    window.clearInterval(timer);
    sub.onClose?.();
  });

  return ctrl;
}

export function subscribeMessageStream(
  messageId: string,
  sub: StreamSubscriber,
): AbortController {
  if (USE_MOCK_API || messageId.startsWith('msg-')) {
    return subscribeMockMessageStream(sub);
  }

  const ctrl = new AbortController();
  const token = useAuthStore.getState().token;

  fetchEventSource(`${BASE_URL}/api/v1/messages/${messageId}/stream`, {
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
