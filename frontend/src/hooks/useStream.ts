/**
 * useStream — React Hook for consuming SSE streams of agent messages.
 *
 * TODO(F): full integration with components/chat/MessageList.
 */

import { useEffect, useRef, useState } from 'react';
import { subscribeMessageStream } from '@/lib/sse';
import type { ContentBlock, StreamEvent } from '@/lib/types';

export type StreamStatus = 'idle' | 'streaming' | 'done' | 'error';

interface StreamingBlock {
  type: ContentBlock['type'];
  text?: string;
  code?: string;
  language?: string;
  [k: string]: unknown;
}

export function useStream(messageId: string | null) {
  const [blocks, setBlocks] = useState<StreamingBlock[]>([]);
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const ctrlRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!messageId) return;
    setBlocks([]);
    setStatus('idle');
    setError(null);

    const ctrl = subscribeMessageStream(messageId, {
      onEvent: (ev: StreamEvent) => {
        switch (ev.event) {
          case 'start':
            setStatus('streaming');
            break;
          case 'block_start': {
            const d = ev.data;
            setBlocks((prev) => {
              const next = [...prev];
              const newBlock: StreamingBlock = {
                type: d.block_type as ContentBlock['type'],
              };
              if (d.block_type === 'code') {
                newBlock.language = (d.metadata?.language as string) || 'text';
                newBlock.code = '';
              } else if (d.block_type === 'text') {
                newBlock.text = '';
              }
              next[d.block_index] = newBlock;
              return next;
            });
            break;
          }
          case 'delta': {
            const d = ev.data;
            setBlocks((prev) => {
              const next = [...prev];
              const b = next[d.block_index];
              if (!b) return next;
              if (d.text_delta) b.text = (b.text || '') + d.text_delta;
              if (d.code_delta) b.code = (b.code || '') + d.code_delta;
              next[d.block_index] = { ...b };
              return next;
            });
            break;
          }
          case 'block_end':
            // no-op for now
            break;
          case 'done':
            setStatus('done');
            ctrl.abort();
            break;
          case 'error':
            setStatus('error');
            setError(ev.data.error || 'unknown error');
            ctrl.abort();
            break;
        }
      },
      onError: (err) => {
        setStatus('error');
        setError(String(err));
      },
    });
    ctrlRef.current = ctrl;

    return () => ctrl.abort();
  }, [messageId]);

  return { blocks, status, error };
}
