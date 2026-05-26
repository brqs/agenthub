import { ContentRenderer } from '@/components/blocks/ContentRenderer';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import type { DemoMessage } from '@/lib/mockData';
import { getAgent } from '@/lib/mockData';
import { cn, formatTime } from '@/lib/utils';
import { Pin, RotateCcw } from 'lucide-react';

export function MessageBubble({
  message,
  highlighted = false,
  onTogglePin,
  onRetry,
}: {
  message: DemoMessage;
  highlighted?: boolean;
  onTogglePin?: (messageId: string) => void;
  onRetry?: (messageId: string) => void;
}) {
  const isUser = message.role === 'user';
  const agent = getAgent(message.agent_id);

  return (
    <article
      className={cn(
        'group flex gap-3 rounded-md px-1 py-1 transition-colors',
        isUser && 'justify-end',
        highlighted && 'bg-brand/10 ring-1 ring-brand/40',
      )}
    >
      {!isUser && (
        <div className="pt-6">
          <AgentAvatar agent={agent} />
        </div>
      )}
      <div className={cn(isUser ? 'order-1 max-w-[min(680px,78%)]' : 'min-w-0 flex-1')}>
        <div className={cn('mb-1.5 flex items-center gap-2 px-1 text-xs text-slate-500', isUser && 'justify-end')}>
          <span className="font-medium text-slate-300">{isUser ? '你' : agent?.name ?? 'Agent'}</span>
          <span>{formatTime(message.created_at)}</span>
          {message.status === 'streaming' && <span className="text-brand-light">正在输入</span>}
          {message.status === 'error' && <span className="text-red-400">需要重试</span>}
          {onTogglePin && (
            <button
              type="button"
              onClick={() => onTogglePin(message.id)}
              className={cn(
                'ml-1 rounded-md p-1 opacity-80 transition hover:bg-slate-800 hover:text-white group-hover:opacity-100',
                message.is_pinned ? 'text-brand-light' : 'text-slate-600',
              )}
              title={message.is_pinned ? '取消 Pin' : 'Pin 消息'}
              aria-label={message.is_pinned ? '取消 Pin' : 'Pin 消息'}
            >
              <Pin className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        <div
          className={cn(
            'min-w-0 overflow-visible rounded-md px-4 py-3 shadow-sm',
            isUser
              ? 'bg-brand text-white shadow-brand/10'
              : message.status === 'error'
                ? 'border border-red-500/30 bg-red-950/20 text-slate-100'
                : 'border border-slate-800 bg-slate-900/75 text-slate-100 shadow-black/10',
          )}
        >
          <ContentRenderer blocks={message.content} streaming={message.status === 'streaming'} />
          {message.status === 'error' && onRetry && (
            <button
              type="button"
              onClick={() => onRetry(message.id)}
              className="mt-3 inline-flex items-center gap-2 rounded-md border border-red-500/30 px-3 py-1.5 text-xs font-medium text-red-100 hover:bg-red-500/10"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              重试
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
