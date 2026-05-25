import { Archive, ArchiveRestore, Hash, Pin, Users } from 'lucide-react';
import type { DemoConversation } from '@/lib/mockData';
import { cn, formatTime } from '@/lib/utils';

export function ConversationItem({
  conversation,
  active,
  onSelect,
  onTogglePin,
  onToggleArchive,
}: {
  conversation: DemoConversation;
  active: boolean;
  onSelect: () => void;
  onTogglePin?: () => void;
  onToggleArchive?: () => void;
}) {
  const ModeIcon = conversation.mode === 'group' ? Users : Hash;
  function handleSelectKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onSelect();
  }

  return (
    <div
      className={cn(
        'group relative flex w-full items-start rounded-md px-3 py-2 transition',
        active
          ? 'bg-slate-800 text-white ring-1 ring-brand/30'
          : 'text-slate-300 hover:bg-slate-800/70 hover:text-white',
      )}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={onSelect}
        onKeyDown={handleSelectKeyDown}
        className="min-w-0 flex-1 cursor-pointer text-left outline-none"
      >
        <div className="flex min-w-0 items-center gap-2">
          <ModeIcon className="h-4 w-4 shrink-0 text-slate-500" />
          <span className="min-w-0 flex-1 truncate text-sm font-medium">{conversation.title}</span>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onTogglePin?.();
            }}
            className={cn(
              'relative z-10 shrink-0 rounded p-0.5 transition hover:bg-slate-700 hover:text-white focus:bg-slate-700 focus:text-white',
              conversation.is_pinned
                ? 'text-brand-light/80'
                : 'text-slate-600 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100',
            )}
            title={conversation.is_pinned ? '取消置顶' : '置顶会话'}
            aria-label={conversation.is_pinned ? '取消置顶' : '置顶会话'}
          >
            <Pin className="h-3.5 w-3.5" />
          </button>
          {conversation.unread_count ? (
            <span className="shrink-0 rounded-full bg-brand px-1.5 text-[10px] font-semibold text-white">
              {conversation.unread_count}
            </span>
          ) : null}
        </div>
        <div className="mt-1 flex items-center gap-2 pl-6 text-xs text-slate-500">
          <span className="truncate">
            {conversation.mode === 'group' ? `${conversation.agent_ids.length} Agents` : conversation.agent_ids[0]}
          </span>
          <span>·</span>
          <span>{formatTime(conversation.last_message_at)}</span>
        </div>
        <p className="mt-1 truncate pl-6 text-xs text-slate-500">
          {conversation.last_message_preview}
        </p>
      </div>
      <div className="pointer-events-none absolute bottom-2 right-2 flex h-7 items-center gap-1 opacity-0 transition group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100">
        {onToggleArchive && (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onToggleArchive();
            }}
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded-md bg-slate-800/95 text-slate-400 shadow-sm ring-1 ring-slate-700 transition hover:bg-slate-700 hover:text-white focus:opacity-100',
              conversation.is_archived && 'text-brand-light',
            )}
            title={conversation.is_archived ? '取消归档' : '归档会话'}
            aria-label={conversation.is_archived ? '取消归档' : '归档会话'}
          >
            {conversation.is_archived ? (
              <ArchiveRestore className="h-3.5 w-3.5" />
            ) : (
              <Archive className="h-3.5 w-3.5" />
            )}
          </button>
        )}
      </div>
    </div>
  );
}
