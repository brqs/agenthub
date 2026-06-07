/**
 * useStream — React Hook for consuming SSE streams of agent messages.
 *
 * TODO(F): full integration with components/chat/MessageList.
 */

import { useEffect, useRef, useState } from 'react';
import { subscribeMessageStream } from '@/lib/sse';
import type { ContentBlock, StreamEvent } from '@/lib/types';

export type StreamStatus = 'idle' | 'streaming' | 'done' | 'error' | 'interrupted';

interface StreamingBlock {
  type: ContentBlock['type'];
  agent_id?: string | null;
  call_id?: string;
  tool_name?: string;
  arguments?: Record<string, unknown>;
  status?:
    | 'pending'
    | 'ok'
    | 'error'
    | 'running'
    | 'done'
    | 'partial'
    | 'waiting'
    | 'resolved'
    | 'cancelled'
    | 'interrupted';
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
    onInterrupted?: () => void;
    onTransportError?: (error: string) => void;
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
            if (eventBelongsToAnotherMessage(messageId, ev)) break;
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
              } else if (d.block_type === 'process') {
                newBlock.agent_id =
                  (d.metadata?.agent_id as string | undefined) ?? d.agent_id ?? 'orchestrator';
                newBlock.title =
                  typeof d.metadata?.title === 'string' ? d.metadata.title : '执行过程';
                newBlock.status = processStatus(d.metadata?.status);
                newBlock.default_collapsed =
                  typeof d.metadata?.default_collapsed === 'boolean'
                    ? d.metadata.default_collapsed
                    : false;
                newBlock.steps = processSteps(d.metadata?.steps);
                newBlock.summary =
                  typeof d.metadata?.summary === 'string' ? d.metadata.summary : null;
                newBlock.metadata = d.metadata?.metadata ?? {};
              } else if (d.block_type === 'clarification') {
                newBlock.agent_id =
                  (d.metadata?.agent_id as string | undefined) ?? d.agent_id ?? 'orchestrator';
                newBlock.mode = clarificationMode(d.metadata?.mode);
                newBlock.title =
                  typeof d.metadata?.title === 'string' ? d.metadata.title : '需求澄清';
                newBlock.status = clarificationStatus(d.metadata?.status);
                newBlock.current_question = clarificationQuestion(d.metadata?.current_question);
                newBlock.questions = clarificationQuestions(d.metadata?.questions);
                newBlock.summary =
                  typeof d.metadata?.summary === 'string' ? d.metadata.summary : null;
                newBlock.metadata = d.metadata?.metadata ?? {};
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
            if (eventBelongsToAnotherMessage(messageId, ev)) break;
            const d = ev.data;
            setBlocks((prev) => {
              const next = [...prev];
              const b = next[d.block_index];
              if (!b) return next;
              if (
                b.type !== 'workflow' &&
                b.type !== 'file' &&
                b.type !== 'process' &&
                b.type !== 'clarification' &&
                d.text_delta
              ) {
                b.text = (b.text || '') + d.text_delta;
              }
              if (
                b.type !== 'workflow' &&
                b.type !== 'file' &&
                b.type !== 'process' &&
                b.type !== 'clarification' &&
                d.code_delta
              ) {
                b.code = (b.code || '') + d.code_delta;
              }
              if (b.type === 'workflow' && (d.text_delta || d.code_delta)) {
                b.raw_definition = (b.raw_definition || '') + (d.text_delta || d.code_delta || '');
              }
              if (b.type === 'process') {
                next[d.block_index] = applyProcessDelta(b, d.metadata);
                return next;
              }
              if (!b.agent_id && d.agent_id) b.agent_id = d.agent_id;
              next[d.block_index] = { ...b };
              return next;
            });
            break;
          }
          case 'block_end':
            if (eventBelongsToAnotherMessage(messageId, ev)) break;
            // no-op for now
            break;
          case 'tool_call':
            if (eventBelongsToAnotherMessage(messageId, ev)) break;
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
            if (eventBelongsToAnotherMessage(messageId, ev)) break;
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
          case 'message_start':
          case 'message_done':
          case 'message_error':
          case 'message_interrupted':
            break;
          case 'done':
            completedRef.current = true;
            setStatus('done');
            optionsRef.current?.onDone?.();
            ctrl.abort();
            break;
          case 'interrupted':
            completedRef.current = true;
            setStatus('interrupted');
            optionsRef.current?.onInterrupted?.();
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
        if (completedRef.current) return;
        completedRef.current = true;
        setStatus('error');
        setError(String(err));
        optionsRef.current?.onTransportError?.(String(err));
      },
      onClose: () => {
        if (completedRef.current) return;
        const message = 'stream closed before done';
        completedRef.current = true;
        setStatus('error');
        setError(message);
        optionsRef.current?.onTransportError?.(message);
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

function processStatus(value: unknown): 'running' | 'done' | 'partial' | 'error' | 'interrupted' {
  if (
    value === 'running' ||
    value === 'done' ||
    value === 'partial' ||
    value === 'error' ||
    value === 'interrupted'
  ) {
    return value;
  }
  return 'done';
}

function processSteps(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((step): step is Record<string, unknown> => Boolean(step && typeof step === 'object'))
    .map((step) => ({
      id: typeof step.id === 'string' ? step.id : undefined,
      label: String(step.label ?? '执行步骤'),
      kind: processStepKind(step.kind),
      status: processStepStatus(step.status),
      detail: typeof step.detail === 'string' ? step.detail : null,
      agent_id: typeof step.agent_id === 'string' ? step.agent_id : null,
    }));
}

function applyProcessDelta(
  block: StreamingBlock,
  metadata: Record<string, unknown> | undefined,
): StreamingBlock {
  const rawDelta = metadata?.process_delta;
  if (!rawDelta || typeof rawDelta !== 'object') return { ...block };
  const delta = rawDelta as Record<string, unknown>;
  if (delta.op === 'upsert_step') {
    const step = processStepFromValue(delta.step);
    if (!step) return { ...block };
    const currentSteps = Array.isArray(block.steps) ? block.steps : [];
    const steps = [...currentSteps];
    if (step.id) {
      const existingIndex = steps.findIndex(
        (item) => Boolean(item && typeof item === 'object') && item.id === step.id,
      );
      if (existingIndex >= 0) {
        steps[existingIndex] = step;
        return { ...block, steps };
      }
    }
    return { ...block, steps: [...steps, step] };
  }
  if (delta.op === 'set_summary') {
    return {
      ...block,
      status: processStatus(delta.status),
      summary: typeof delta.summary === 'string' ? delta.summary : block.summary,
    };
  }
  return { ...block };
}

function processStepFromValue(value: unknown) {
  if (!value || typeof value !== 'object') return null;
  const step = value as Record<string, unknown>;
  return {
    id: typeof step.id === 'string' ? step.id : undefined,
    label: String(step.label ?? '执行步骤'),
    kind: processStepKind(step.kind),
    status: processStepStatus(step.status),
    detail: typeof step.detail === 'string' ? step.detail : null,
    agent_id: typeof step.agent_id === 'string' ? step.agent_id : null,
  };
}

function eventBelongsToAnotherMessage(messageId: string, event: StreamEvent): boolean {
  const data = event.data as { message_id?: unknown };
  return typeof data.message_id === 'string' && data.message_id !== messageId;
}

function processStepStatus(
  value: unknown,
): 'done' | 'running' | 'error' | 'skipped' | 'interrupted' {
  if (
    value === 'done' ||
    value === 'running' ||
    value === 'error' ||
    value === 'skipped' ||
    value === 'interrupted'
  ) {
    return value;
  }
  return 'done';
}

function processStepKind(value: unknown) {
  const allowed = [
    'routing',
    'planning',
    'dispatch',
    'tool',
    'review',
    'evaluation',
    'workflow',
    'deployment',
    'artifact',
    'repair',
    'summary',
  ] as const;
  return typeof value === 'string' && allowed.includes(value as (typeof allowed)[number])
    ? value
    : 'summary';
}

function clarificationMode(value: unknown) {
  if (
    value === 'auto' ||
    value === 'grill_me' ||
    value === 'grill_with_docs' ||
    value === 'setup_matt_pocock_skills'
  ) {
    return value;
  }
  return 'auto';
}

function clarificationStatus(value: unknown) {
  if (value === 'waiting' || value === 'resolved' || value === 'cancelled') {
    return value;
  }
  return 'waiting';
}

function clarificationQuestion(value: unknown) {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  return {
    id: String(raw.id ?? 'question'),
    question: String(raw.question ?? ''),
    reason: typeof raw.reason === 'string' ? raw.reason : null,
    recommended_answer:
      typeof raw.recommended_answer === 'string' ? raw.recommended_answer : null,
    options: Array.isArray(raw.options)
      ? raw.options.filter((item): item is string => typeof item === 'string')
      : [],
    status:
      raw.status === 'answered' || raw.status === 'skipped' || raw.status === 'pending'
        ? raw.status
        : 'pending',
    answer: typeof raw.answer === 'string' ? raw.answer : null,
  };
}

function clarificationQuestions(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value.map((item) => clarificationQuestion(item)).filter(Boolean);
}
