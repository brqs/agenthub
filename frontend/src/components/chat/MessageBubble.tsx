import { ContentRenderer } from '@/components/blocks/ContentRenderer';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import type { DemoMessage } from '@/lib/mockData';
import { getAgent } from '@/lib/mockData';
import { cn, formatTime } from '@/lib/utils';

export function MessageBubble({ message }: { message: DemoMessage }) {
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
        </div>
        <div
          className={cn(
            'rounded-md px-4 py-3 shadow-sm',
            isUser
              ? 'bg-brand text-white'
              : 'border border-slate-800 bg-slate-900/80 text-slate-100',
          )}
        >
          <ContentRenderer blocks={message.content} streaming={message.status === 'streaming'} />
        </div>
      </div>
    </article>
  );
}

