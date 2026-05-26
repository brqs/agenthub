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

const DEFAULT_MOCK_REPLY =
  '收到。我会沿用真实 SSE 事件格式来模拟后端：start、block_start、delta、block_end、done 都会经过同一个 useStream 管线。';

const ORCHESTRATOR_REPLY =
  '我先把任务拆成三个协作步骤，并把实现与审查分别交给合适的 Agent。当前 Demo 里这些事件仍然走同一条 SSE 管线，后续可以无缝替换为真实后端。';

const CODE_REPLY = `export function DemoTaskSummary() {
  return (
    <section className="rounded-md border border-slate-800 bg-slate-950 p-4">
      <h2 className="text-sm font-semibold text-white">AgentHub 协作结果</h2>
      <p className="mt-2 text-sm text-slate-400">
        Orchestrator 已完成任务拆解，Frontend Agent 正在输出产物。
      </p>
    </section>
  );
}`;

function textDeltaEvents(text: string, blockIndex: number): StreamEvent[] {
  return Array.from({ length: Math.ceil(text.length / 2) }, (_, index) => ({
    event: 'delta' as const,
    data: {
      block_index: blockIndex,
      text_delta: text.slice(index * 2, index * 2 + 2),
    },
  }));
}

function codeDeltaEvents(code: string, blockIndex: number): StreamEvent[] {
  return Array.from({ length: Math.ceil(code.length / 5) }, (_, index) => ({
    event: 'delta' as const,
    data: {
      block_index: blockIndex,
      code_delta: code.slice(index * 5, index * 5 + 5),
    },
  }));
}

function buildMockEvents(messageId: string): StreamEvent[] {
  if (messageId.startsWith('msg-orchestrator-')) {
    return [
      { event: 'start', data: { agent_id: 'orchestrator' } },
      {
        event: 'block_start',
        data: {
          block_index: 0,
          block_type: 'task_card',
          metadata: {
            title: '群聊协作任务流',
            tasks: [
              { id: 'task-plan', agent_id: 'orchestrator', title: '拆解目标并确定执行顺序', status: 'running' },
              { id: 'task-ui', agent_id: 'web-designer', title: '确认界面表达和演示重点', status: 'pending' },
              { id: 'task-code', agent_id: 'codex-helper', title: '输出可落地的前端实现片段', status: 'pending' },
            ],
          },
        },
      },
      { event: 'block_end', data: { block_index: 0 } },
      { event: 'block_start', data: { block_index: 1, block_type: 'text' } },
      ...textDeltaEvents(ORCHESTRATOR_REPLY, 1),
      { event: 'block_end', data: { block_index: 1 } },
      {
        event: 'tool_call',
        data: {
          call_id: 'stream-write-demo-html',
          tool_name: 'write_file',
          tool_arguments: {
            path: 'public/demo.html',
            content_preview: '<!doctype html><html lang="zh-CN">...',
          },
        },
      },
      {
        event: 'tool_result',
        data: {
          call_id: 'stream-write-demo-html',
          tool_status: 'ok',
          tool_output: 'wrote 4598 bytes to public/demo.html',
        },
      },
      {
        event: 'agent_switch',
        data: {
          from_agent: 'orchestrator',
          to_agent: 'web-designer',
          task: '补充群聊任务流的视觉层级和状态反馈',
        },
      },
      { event: 'block_start', data: { block_index: 4, block_type: 'text' } },
      ...textDeltaEvents('视觉上建议把任务卡作为主线索，Agent 切换作为聊天流里的轻量分隔，避免抢走消息正文的注意力。', 4),
      { event: 'block_end', data: { block_index: 4 } },
      {
        event: 'tool_call',
        data: {
          call_id: 'stream-bash-build',
          tool_name: 'bash',
          tool_arguments: {
            command: 'pnpm build',
            cwd: '.',
          },
        },
      },
      {
        event: 'tool_result',
        data: {
          call_id: 'stream-bash-build',
          tool_status: 'ok',
          tool_output: 'vite build completed in 1.42s',
        },
      },
      {
        event: 'agent_switch',
        data: {
          from_agent: 'web-designer',
          to_agent: 'codex-helper',
          task: '根据任务拆解输出可复制的 React 片段',
        },
      },
      {
        event: 'block_start',
        data: { block_index: 7, block_type: 'code', metadata: { language: 'tsx' } },
      },
      ...codeDeltaEvents(CODE_REPLY, 7),
      { event: 'block_end', data: { block_index: 7 } },
      { event: 'done', data: { total_blocks: 8 } },
    ];
  }

  return [
    { event: 'start', data: {} },
    { event: 'block_start', data: { block_index: 0, block_type: 'text' } },
    ...textDeltaEvents(DEFAULT_MOCK_REPLY, 0),
    { event: 'block_end', data: { block_index: 0 } },
    { event: 'done', data: { total_blocks: 1 } },
  ];
}

function subscribeMockMessageStream(messageId: string, sub: StreamSubscriber): AbortController {
  const ctrl = new AbortController();
  const events = buildMockEvents(messageId);

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
  // Mock SSE for: explicit mock mode, OR mock-shaped IDs (msg-*) emitted by
  // chatStore.createPendingExchange. Real backend uses UUIDs.
  if (env.useMockSse || messageId.startsWith('msg-')) {
    return subscribeMockMessageStream(messageId, sub);
  }

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
