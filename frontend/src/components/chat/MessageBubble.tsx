import { ContentRenderer } from '@/components/blocks/ContentRenderer';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import type { DemoMessage } from '@/lib/mockData';
import type { Agent } from '@/lib/types';
import { cn, formatTime } from '@/lib/utils';
import { Pin, RotateCcw } from 'lucide-react';
import { useEffect, useState } from 'react';

export function MessageBubble({
  message,
  highlighted = false,
  onTogglePin,
  onRetry,
  onMentionAgent,
  agents = [],
}: {
  message: DemoMessage;
  highlighted?: boolean;
  onTogglePin?: (messageId: string) => void;
  onRetry?: (messageId: string) => void;
  onMentionAgent?: (agent: Agent) => void;
  agents?: Agent[];
}) {
  const isUser = message.role === 'user';
  const agent = agents.find((item) => item.id === message.agent_id);
  const [mentionMenuPosition, setMentionMenuPosition] = useState<{ x: number; y: number } | null>(null);
  const canMentionAgent = !isUser && agent !== undefined && onMentionAgent !== undefined;

  useEffect(() => {
    if (!mentionMenuPosition) return undefined;

    function closeMenu() {
      setMentionMenuPosition(null);
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') closeMenu();
    }

    window.addEventListener('click', closeMenu);
    window.addEventListener('scroll', closeMenu, true);
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      window.removeEventListener('click', closeMenu);
      window.removeEventListener('scroll', closeMenu, true);
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, [mentionMenuPosition]);

  function openMentionMenu(event: React.MouseEvent<HTMLDivElement>) {
    if (!canMentionAgent) return;
    event.preventDefault();
    setMentionMenuPosition({ x: event.clientX, y: event.clientY });
  }

  function mentionAgent() {
    if (!agent || !onMentionAgent) return;
    onMentionAgent(agent);
    setMentionMenuPosition(null);
  }

  return (
    <article
      className={cn(
        'group flex gap-3 rounded-md px-1 py-1 transition-colors',
        isUser && 'justify-end',
        highlighted && 'bg-brand/10 ring-1 ring-brand/40',
      )}
    >
      {!isUser && (
        <div
          className={cn('pt-6', canMentionAgent && 'cursor-context-menu')}
          onContextMenu={openMentionMenu}
          title={canMentionAgent ? `右键 @${agent.name}` : undefined}
        >
          <AgentAvatar agent={agent} />
        </div>
      )}
      <div className={cn(isUser ? 'order-1 flex max-w-[min(680px,78%)] flex-col items-end' : 'min-w-0 flex-1')}>
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
                'ml-1 rounded-md p-1 transition hover:bg-slate-800 hover:text-white group-hover:opacity-100',
                message.is_pinned ? 'text-brand-light opacity-100' : 'text-slate-600 opacity-0',
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
              ? 'user-message-bubble w-fit max-w-full bg-brand px-4 py-2.5 text-white shadow-brand/10'
              : message.status === 'error'
                ? 'border border-red-500/30 bg-red-950/20 text-slate-100'
                : 'border border-slate-800 bg-slate-900/75 text-slate-100 shadow-black/10',
          )}
        >
          <ContentRenderer
            blocks={message.content}
            agents={agents}
            streaming={message.status === 'streaming'}
          />
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
      {mentionMenuPosition && agent && (
        <div
          role="menu"
          className="fixed z-50 min-w-40 overflow-hidden rounded-md border border-slate-700 bg-slate-900 p-1 shadow-xl shadow-black/30"
          style={{ left: mentionMenuPosition.x, top: mentionMenuPosition.y }}
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            role="menuitem"
            onClick={mentionAgent}
            className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-slate-200 transition hover:bg-brand/15 hover:text-brand-light"
          >
            @ {agent.name}
          </button>
        </div>
      )}
    </article>
  );
}
