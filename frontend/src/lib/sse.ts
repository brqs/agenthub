/**
 * SSE client wrapping @microsoft/fetch-event-source.
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

interface StreamSession {
  ctrl: AbortController;
  subscribers: Set<StreamSubscriber>;
  releaseTimer: number | null;
  intentionalClose: boolean;
  completed: boolean;
}

const STREAM_RELEASE_DELAY_MS = 500;
const streamSessions = new Map<string, StreamSession>();

async function streamOpenError(response: Response): Promise<Error> {
  let message = `SSE open failed: ${response.status}`;
  try {
    const body = await response.json();
    const detail = body?.detail?.error;
    if (detail?.code || detail?.message) {
      message = `${detail.code ?? response.status}: ${detail.message ?? message}`;
    }
  } catch {
    // Keep the status-only fallback for non-JSON errors.
  }
  if (response.status === 409 || response.status === 401 || response.status === 403) {
    return new FatalError(message);
  }
  return new Error(message);
}

export function subscribeMessageStream(
  messageId: string,
  sub: StreamSubscriber,
): AbortController {
  let session = streamSessions.get(messageId);
  if (session) {
    if (session.releaseTimer !== null) {
      window.clearTimeout(session.releaseTimer);
      session.releaseTimer = null;
    }
    session.subscribers.add(sub);
    return subscriptionController(messageId, sub);
  }

  const ctrl = new AbortController();
  session = {
    ctrl,
    subscribers: new Set([sub]),
    releaseTimer: null,
    intentionalClose: false,
    completed: false,
  };
  streamSessions.set(messageId, session);
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
      throw await streamOpenError(response);
    },
    onmessage(msg: EventSourceMessage) {
      const current = streamSessions.get(messageId);
      if (!current) return;
      try {
        const data = msg.data ? JSON.parse(msg.data) : {};
        const event = { event: msg.event as StreamEvent['event'], data } as StreamEvent;
        if (event.event === 'done' || event.event === 'error') {
          current.completed = true;
        }
        for (const subscriber of current.subscribers) {
          subscriber.onEvent(event);
        }
      } catch (e) {
        for (const subscriber of current.subscribers) {
          subscriber.onError?.(e);
        }
      }
    },
    onerror(err) {
      if (err instanceof FatalError) {
        throw err;
      }
    },
    onclose() {
      const current = streamSessions.get(messageId);
      if (!current) return;
      streamSessions.delete(messageId);
      if (current.intentionalClose || current.completed) return;
      for (const subscriber of current.subscribers) {
        subscriber.onClose?.();
      }
    },
  }).catch((err) => {
    const current = streamSessions.get(messageId);
    if (!current) return;
    streamSessions.delete(messageId);
    if (current.intentionalClose || current.completed || isAbortError(err)) return;
    for (const subscriber of current.subscribers) {
      subscriber.onError?.(err);
    }
  });

  return subscriptionController(messageId, sub);
}

function subscriptionController(messageId: string, sub: StreamSubscriber): AbortController {
  const ctrl = new AbortController();
  ctrl.signal.addEventListener(
    'abort',
    () => {
      const session = streamSessions.get(messageId);
      if (!session) return;
      session.subscribers.delete(sub);
      if (session.subscribers.size > 0) return;
      session.releaseTimer = window.setTimeout(() => {
        const current = streamSessions.get(messageId);
        if (!current || current.subscribers.size > 0) return;
        current.intentionalClose = true;
        current.ctrl.abort();
        streamSessions.delete(messageId);
      }, STREAM_RELEASE_DELAY_MS);
    },
    { once: true },
  );
  return ctrl;
}

function isAbortError(err: unknown): boolean {
  if (err instanceof DOMException && err.name === 'AbortError') return true;
  return err instanceof Error && err.name === 'AbortError';
}
