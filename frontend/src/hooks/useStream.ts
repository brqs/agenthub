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
  agent_id?: string | null;
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
  raw_definition?: string;
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
                agent_id: d.agent_id ?? null,
              };
              if (d.block_type === 'code') {
                newBlock.language = (d.metadata?.language as string) || 'text';
                newBlock.code = '';
              } else if (d.block_type === 'text') {
                newBlock.text = '';
              } else if (d.block_type === 'workflow') {
                newBlock.raw_definition = '';
                newBlock.last_run_id = (d.metadata?.last_run_id as string) || null;
                newBlock.format = d.metadata?.format === 'json' ? 'json' : 'yaml';
                newBlock.validation_status = d.metadata?.validation_status ?? 'unknown';
                newBlock.runtime_status = d.metadata?.runtime_status ?? 'not_supported';
                newBlock.dry_run_status = d.metadata?.dry_run_status ?? 'not_supported';
                newBlock.health_status = d.metadata?.health_status ?? 'unknown';
              } else if (d.block_type === 'file') {
                newBlock.path = (d.metadata?.path as string) || null;
                newBlock.artifact_kind = d.metadata?.artifact_kind ?? 'other';
                newBlock.filename = (d.metadata?.filename as string) || 'artifact';
                newBlock.url = (d.metadata?.url as string) || '';
                newBlock.size = (d.metadata?.size as number) || 0;
                newBlock.mime_type =
                  (d.metadata?.mime_type as string) || 'application/octet-stream';
                newBlock.preview_text = (d.metadata?.preview_text as string) || null;
                newBlock.preview_truncated = d.metadata?.preview_truncated ?? false;
                newBlock.metadata = d.metadata?.metadata ?? {};
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
              if (b.type !== 'workflow' && b.type !== 'file' && d.text_delta) {
                b.text = (b.text || '') + d.text_delta;
              }
              if (b.type !== 'workflow' && b.type !== 'file' && d.code_delta) {
                b.code = (b.code || '') + d.code_delta;
              }
              if (b.type === 'workflow' && (d.text_delta || d.code_delta)) {
                b.raw_definition = (b.raw_definition || '') + (d.text_delta || d.code_delta || '');
              }
              if (!b.agent_id && d.agent_id) b.agent_id = d.agent_id;
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
                agent_id: ev.data.agent_id ?? null,
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
                      agent_id: block.agent_id ?? ev.data.agent_id ?? null,
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
