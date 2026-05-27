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
  call_id?: string;
  tool_name?: string;
  arguments?: Record<string, unknown>;
  status?: 'pending' | 'ok' | 'error';
  text?: string;
  code?: string;
  language?: string;
  output_preview?: string;
  output_truncated?: boolean;
  error_code?: string;
  [k: string]: unknown;
}

export function useStream(
  messageId: string | null,
  options?: {
    onEvent?: (event: StreamEvent) => void;
    onDone?: () => void;
    onError?: (error: string) => void;
  },
) {
  const [blocks, setBlocks] = useState<StreamingBlock[]>([]);
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const ctrlRef = useRef<AbortController | null>(null);
  const completedRef = useRef(false);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    if (!messageId) return;
    setBlocks([]);
    setStatus('idle');
    setError(null);
    completedRef.current = false;

    const ctrl = subscribeMessageStream(messageId, {
      onEvent: (ev: StreamEvent) => {
        optionsRef.current?.onEvent?.(ev);
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
          case 'tool_call':
            setBlocks((prev) => [
              ...prev,
              {
                type: 'tool_call',
                call_id: ev.data.call_id,
                tool_name: ev.data.tool_name,
                arguments: ev.data.tool_arguments,
                status: 'pending',
              },
            ]);
            break;
          case 'tool_result':
            setBlocks((prev) =>
              prev.map((block) =>
                block.type === 'tool_call' && block.call_id === ev.data.call_id
                  ? {
                      ...block,
                      status: ev.data.tool_status,
                      output_preview: ev.data.tool_output,
                      output_truncated: ev.data.tool_output_truncated,
                      error_code: ev.data.error_code,
                    }
                  : block,
              ),
            );
            break;
          case 'heartbeat':
            break;
          case 'done':
            completedRef.current = true;
            setStatus('done');
            optionsRef.current?.onDone?.();
            ctrl.abort();
            break;
          case 'error':
            completedRef.current = true;
            setStatus('error');
            setError(ev.data.error || 'unknown error');
            optionsRef.current?.onError?.(ev.data.error || 'unknown error');
            ctrl.abort();
            break;
        }
      },
      onError: (err) => {
        completedRef.current = true;
        setStatus('error');
        setError(String(err));
        optionsRef.current?.onError?.(String(err));
      },
      onClose: () => {
        if (completedRef.current) return;
        const message = 'stream closed before done';
        completedRef.current = true;
        setStatus('error');
        setError(message);
        optionsRef.current?.onError?.(message);
      },
    });
    ctrlRef.current = ctrl;

    return () => {
      completedRef.current = true;
      ctrl.abort();
    };
  }, [messageId]);

  return { blocks, status, error };
}
