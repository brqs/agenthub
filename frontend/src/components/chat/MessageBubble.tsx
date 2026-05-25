import { ContentRenderer } from '@/components/blocks/ContentRenderer';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import type { DemoMessage } from '@/lib/mockData';
import { getAgent } from '@/lib/mockData';
import { cn, formatTime } from '@/lib/utils';
import { RotateCcw } from 'lucide-react';

export function MessageBubble({
  message,
  onRetry,
}: {
  message: DemoMessage;
  onRetry?: (messageId: string) => void;
}) {
  const isUser = message.role === 'user';
  const agent = getAgent(message.agent_id);

  return (
    <article className={cn('flex gap-3', isUser && 'justify-end')}>
      {!isUser && <AgentAvatar agent={agent} />}
      <div className={cn('max-w-3xl', isUser ? 'order-1' : 'min-w-0 flex-1')}>
        <div className={cn('mb-1 flex items-center gap-2 text-xs text-slate-500', isUser && 'justify-end')}>
          <span className="font-medium text-slate-300">{isUser ? '你' : agent?.name ?? 'Agent'}</span>
          <span>{formatTime(message.created_at)}</span>
          {message.status === 'streaming' && <span className="text-brand-light">正在输入</span>}
          {message.status === 'error' && <span className="text-red-400">需要重试</span>}
        </div>
        <div
          className={cn(
            'rounded-md px-4 py-3 shadow-sm',
            isUser
              ? 'bg-brand text-white'
              : message.status === 'error'
                ? 'border border-red-500/30 bg-red-950/20 text-slate-100'
                : 'border border-slate-800 bg-slate-900/80 text-slate-100',
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
