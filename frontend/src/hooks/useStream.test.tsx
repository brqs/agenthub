import { renderHook, waitFor } from '@testing-library/react';
import { useStream } from './useStream';
import { subscribeMessageStream, type StreamSubscriber } from '@/lib/sse';

vi.mock('@/lib/sse', () => ({
  subscribeMessageStream: vi.fn(),
}));

const subscribeMessageStreamMock = vi.mocked(subscribeMessageStream);

function mockStream(setup: (subscriber: StreamSubscriber) => void) {
  subscribeMessageStreamMock.mockImplementation((_messageId, subscriber) => {
    const controller = new AbortController();
    window.setTimeout(() => setup(subscriber), 0);
    return controller;
  });
}

describe('useStream', () => {
  beforeEach(() => {
    subscribeMessageStreamMock.mockReset();
  });

  it('tracks tool call and tool result events', async () => {
    mockStream((subscriber) => {
      subscriber.onEvent({ event: 'start', data: {} });
      subscriber.onEvent({
        event: 'tool_call',
        data: {
          call_id: 'call-write',
          tool_name: 'write_file',
          tool_arguments: { path: 'demo.html' },
        },
      });
      subscriber.onEvent({
        event: 'tool_result',
        data: {
          call_id: 'call-write',
          tool_status: 'ok',
          tool_output: 'wrote file',
        },
      });
      subscriber.onEvent({ event: 'done', data: { total_blocks: 1 } });
    });

    const { result } = renderHook(() => useStream('message-1'));

    await waitFor(() => expect(result.current.status).toBe('done'));
    expect(result.current.blocks).toEqual([
      {
        type: 'tool_call',
        agent_id: null,
        presentation: null,
        call_id: 'call-write',
        tool_name: 'write_file',
        arguments: { path: 'demo.html' },
        status: 'ok',
        output_preview: 'wrote file',
        output_truncated: undefined,
        error_code: undefined,
      },
    ]);
  });

  it('preserves presentation metadata on stream blocks and tool calls', async () => {
    mockStream((subscriber) => {
      subscriber.onEvent({ event: 'start', data: {} });
      subscriber.onEvent({
        event: 'block_start',
        data: {
          block_index: 0,
          block_type: 'text',
          metadata: {
            presentation: {
              role: 'final_answer',
              collapsible: false,
              boundary: 'answer_start',
              closes_group_id: 'execution-main',
            },
          },
        },
      });
      subscriber.onEvent({ event: 'delta', data: { block_index: 0, text_delta: 'done' } });
      subscriber.onEvent({
        event: 'tool_call',
        data: {
          call_id: 'call-read',
          tool_name: 'Read',
          tool_arguments: {},
          metadata: {
            presentation: {
              role: 'tool_trace',
              collapsible: true,
              group_id: 'execution-main',
            },
          },
        },
      });
      subscriber.onEvent({ event: 'done', data: { total_blocks: 2 } });
    });

    const { result } = renderHook(() => useStream('message-presentation'));

    await waitFor(() => expect(result.current.status).toBe('done'));
    expect(result.current.blocks[0]).toMatchObject({
      type: 'text',
      text: 'done',
      presentation: {
        role: 'final_answer',
        collapsible: false,
        boundary: 'answer_start',
        closes_group_id: 'execution-main',
      },
    });
    expect(result.current.blocks[1]).toMatchObject({
      type: 'tool_call',
      call_id: 'call-read',
      presentation: {
        role: 'tool_trace',
        collapsible: true,
        group_id: 'execution-main',
      },
    });
  });

  it('reports a recoverable error when a stream closes before done', async () => {
    const onTransportError = vi.fn();
    mockStream((subscriber) => {
      subscriber.onEvent({ event: 'start', data: {} });
      subscriber.onClose?.();
    });

    const { result } = renderHook(() => useStream('message-2', { onTransportError }));

    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error).toBe('stream closed before done');
    expect(onTransportError).toHaveBeenCalledWith('stream closed before done');
  });

  it('keeps process blocks from metadata and applies process deltas', async () => {
    mockStream((subscriber) => {
      subscriber.onEvent({ event: 'start', data: {} });
      subscriber.onEvent({
        event: 'block_start',
        data: {
          block_index: 0,
          block_type: 'process',
          agent_id: 'orchestrator',
          metadata: {
            title: '执行过程',
            status: 'running',
            default_collapsed: false,
            steps: [{ id: 'route', label: '直接回答', kind: 'routing', status: 'running' }],
          },
        },
      });
      subscriber.onEvent({
        event: 'delta',
        data: {
          block_index: 0,
          metadata: {
            process_delta: {
              op: 'upsert_step',
              step: { id: 'route', label: '直接回答', kind: 'routing', status: 'done' },
            },
          },
        },
      });
      subscriber.onEvent({
        event: 'delta',
        data: {
          block_index: 0,
          metadata: {
            process_delta: {
              op: 'set_summary',
              status: 'done',
              summary: '公开执行过程已完成。',
            },
          },
        },
      });
      subscriber.onEvent({ event: 'done', data: { total_blocks: 1 } });
    });

    const { result } = renderHook(() => useStream('message-process'));

    await waitFor(() => expect(result.current.status).toBe('done'));
    expect(result.current.blocks[0]).toMatchObject({
      type: 'process',
      agent_id: 'orchestrator',
      title: '执行过程',
      status: 'done',
      summary: '公开执行过程已完成。',
      steps: [{ id: 'route', label: '直接回答', kind: 'routing', status: 'done' }],
    });
    expect(result.current.blocks[0]).not.toHaveProperty('text');
  });

  it('does not merge child message blocks into the parent stream block list', async () => {
    mockStream((subscriber) => {
      subscriber.onEvent({ event: 'start', data: { message_id: 'parent-message' } });
      subscriber.onEvent({
        event: 'message_start',
        data: {
          message_id: 'child-message',
          conversation_id: 'conv-1',
          agent_id: 'codex-helper',
          status: 'streaming',
        },
      });
      subscriber.onEvent({
        event: 'block_start',
        data: {
          message_id: 'child-message',
          block_index: 0,
          block_type: 'text',
          agent_id: 'codex-helper',
        },
      });
      subscriber.onEvent({
        event: 'delta',
        data: {
          message_id: 'child-message',
          block_index: 0,
          text_delta: 'child text',
          agent_id: 'codex-helper',
        },
      });
      subscriber.onEvent({ event: 'message_done', data: { message_id: 'child-message' } });
      subscriber.onEvent({ event: 'done', data: { message_id: 'parent-message' } });
    });

    const { result } = renderHook(() => useStream('parent-message'));

    await waitFor(() => expect(result.current.status).toBe('done'));
    expect(result.current.blocks).toEqual([]);
  });

  it('does not report close errors after done', async () => {
    const onError = vi.fn();
    mockStream((subscriber) => {
      subscriber.onEvent({ event: 'start', data: {} });
      subscriber.onEvent({ event: 'done', data: {} });
      subscriber.onClose?.();
    });

    const { result } = renderHook(() => useStream('message-3', { onError }));

    await waitFor(() => expect(result.current.status).toBe('done'));
    expect(onError).not.toHaveBeenCalled();
  });

  it('does not report transport errors after done', async () => {
    const onTransportError = vi.fn();
    mockStream((subscriber) => {
      subscriber.onEvent({ event: 'start', data: {} });
      subscriber.onEvent({ event: 'done', data: {} });
      subscriber.onError?.(new Error('abort after done'));
    });

    const { result } = renderHook(() => useStream('message-4', { onTransportError }));

    await waitFor(() => expect(result.current.status).toBe('done'));
    expect(onTransportError).not.toHaveBeenCalled();
  });
});
