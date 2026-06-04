import { Bot, Loader2, MessageSquarePlus } from 'lucide-react';
import { useLayoutEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import type { DemoMessage } from '@/lib/mockData';
import type { Agent } from '@/lib/types';

export function MessageList({
  messages,
  highlightedMessageId,
  isLoading = false,
  isLoadingMore = false,
  hasMore = false,
  onLoadMore,
  onTogglePin,
  onRetry,
  retryingMessageIds = {},
  onMentionAgent,
  agents = [],
}: {
  messages: DemoMessage[];
  highlightedMessageId?: string | null;
  isLoading?: boolean;
  isLoadingMore?: boolean;
  hasMore?: boolean;
  onLoadMore?: () => void;
  onTogglePin?: (messageId: string) => void;
  onRetry?: (messageId: string) => void;
  retryingMessageIds?: Record<string, boolean>;
  onMentionAgent?: (agent: Agent) => void;
  agents?: Agent[];
}) {
  const endRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const restoreScrollHeightRef = useRef<number | null>(null);
  const nearBottomRef = useRef(true);

  useLayoutEffect(() => {
    const scrollEl = scrollRef.current;
    if (!scrollEl) return;

    if (restoreScrollHeightRef.current !== null) {
      const previousHeight = restoreScrollHeightRef.current;
      restoreScrollHeightRef.current = null;
      scrollEl.scrollTop += scrollEl.scrollHeight - previousHeight;
      return;
    }

    if (nearBottomRef.current) {
      endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' });
    }
  }, [messages]);

  function handleScroll() {
    const scrollEl = scrollRef.current;
    if (!scrollEl) return;
    nearBottomRef.current =
      scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight < 120;
    if (scrollEl.scrollTop > 80 || !hasMore || isLoadingMore) return;
    restoreScrollHeightRef.current = scrollEl.scrollHeight;
    onLoadMore?.();
  }

  if (isLoading) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center bg-slate-950 px-6 py-6 text-slate-500">
        <div className="flex items-center gap-3 text-sm">
          <Loader2 className="h-4 w-4 animate-spin text-brand-light" />
          正在加载消息
        </div>
      </div>
    );
  }

  if (!messages.length) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center bg-slate-950 px-6 py-6">
        <div className="max-w-sm text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-md border border-slate-800 bg-slate-900 text-brand-light">
            <MessageSquarePlus className="h-5 w-5" />
          </div>
          <h3 className="mt-4 text-sm font-semibold text-white">开始一段新协作</h3>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            发送第一条消息，或在群聊中输入 @ 指定 Agent。
          </p>
          <div className="mt-4 inline-flex items-center gap-2 rounded-md bg-slate-900 px-3 py-2 text-xs text-slate-500">
            <Bot className="h-3.5 w-3.5" />
            真后端 SSE 会流式返回 Agent 回复
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="min-h-0 flex-1 overflow-y-auto px-3 py-4 scrollbar-thin sm:px-6 sm:py-5 [@media(max-height:800px)]:py-4"
    >
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {(hasMore || isLoadingMore) && (
          <div className="flex justify-center py-2 text-xs text-slate-500">
            {isLoadingMore ? (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                正在加载更早消息
              </span>
            ) : (
              <button
                type="button"
                onClick={() => {
                  const scrollEl = scrollRef.current;
                  if (scrollEl) restoreScrollHeightRef.current = scrollEl.scrollHeight;
                  onLoadMore?.();
                }}
                className="rounded-md border border-slate-800 px-3 py-1.5 text-slate-400 transition hover:border-slate-700 hover:text-slate-200"
              >
                加载更早消息
              </button>
            )}
          </div>
        )}
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            agents={agents}
            highlighted={message.id === highlightedMessageId}
            onTogglePin={onTogglePin}
            onRetry={onRetry}
            isRetrying={Boolean(retryingMessageIds[message.id])}
            onMentionAgent={onMentionAgent}
          />
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
