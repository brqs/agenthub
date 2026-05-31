import { Bot, Loader2, MessageSquarePlus } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import type { DemoMessage } from '@/lib/mockData';
import { env } from '@/lib/env';
import type { Agent } from '@/lib/types';

export function MessageList({
  messages,
  highlightedMessageId,
  isLoading = false,
  onTogglePin,
  onRetry,
  onMentionAgent,
  agents = [],
}: {
  messages: DemoMessage[];
  highlightedMessageId?: string | null;
  isLoading?: boolean;
  onTogglePin?: (messageId: string) => void;
  onRetry?: (messageId: string) => void;
  onMentionAgent?: (agent: Agent) => void;
  agents?: Agent[];
}) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

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
            {env.useMockSse ? 'Mock SSE 会模拟流式回复' : '真后端 SSE 会流式返回 Agent 回复'}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5 scrollbar-thin max-[800px]:px-4 max-[800px]:py-4 [@media(max-height:800px)]:py-4">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            agents={agents}
            highlighted={message.id === highlightedMessageId}
            onTogglePin={onTogglePin}
            onRetry={onRetry}
            onMentionAgent={onMentionAgent}
          />
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
