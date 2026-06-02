import { Archive, ArchiveRestore, Hash, MoreHorizontal, Pin, Users } from 'lucide-react';
import { useState } from 'react';
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
  const lastMessageTime = formatTime(conversation.last_message_at);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

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
          ? 'bg-brand/10 text-slate-950 ring-1 ring-brand/25 dark:bg-slate-800 dark:text-white dark:ring-brand/30'
          : 'text-slate-700 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-slate-800/70 dark:hover:text-white',
      )}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={onSelect}
        onKeyDown={handleSelectKeyDown}
        className="min-w-0 flex-1 cursor-pointer text-left outline-none"
      >
        <div className="flex min-w-0 items-center gap-2 pr-[4.75rem]">
          <ModeIcon className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-500" />
          <span className="min-w-0 flex-1 truncate text-sm font-medium">{conversation.title}</span>
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
        </div>
        <p className="mt-1 truncate pl-6 text-xs text-slate-500">
          {conversation.last_message_preview}
        </p>
      </div>
      <div
        className="pointer-events-none absolute right-2 top-2 flex h-7 w-[4.25rem] items-center justify-end text-xs text-slate-500 transition group-hover:opacity-0 group-focus-within:opacity-0"
        aria-label={`最后消息时间 ${lastMessageTime}`}
      >
        <span className="truncate">{lastMessageTime}</span>
      </div>
      <div className="pointer-events-none absolute right-2 top-2 flex h-7 w-[4.25rem] items-center justify-end gap-1 opacity-0 transition group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100">
        {onTogglePin && (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onTogglePin();
            }}
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded-md bg-white/95 text-slate-500 shadow-sm ring-1 ring-slate-300 transition hover:bg-slate-100 hover:text-slate-950 focus:bg-slate-100 focus:text-slate-950 focus:outline-none focus:ring-2 focus:ring-brand dark:bg-slate-800/95 dark:text-slate-400 dark:ring-slate-700 dark:hover:bg-slate-700 dark:hover:text-white dark:focus:bg-slate-700 dark:focus:text-white',
              conversation.is_pinned && 'text-brand dark:text-brand-light',
            )}
            title={conversation.is_pinned ? '取消置顶' : '置顶会话'}
            aria-label={conversation.is_pinned ? '取消置顶' : '置顶会话'}
          >
            <Pin className="h-3.5 w-3.5" />
          </button>
        )}
        {onToggleArchive && (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onToggleArchive();
            }}
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded-md bg-white/95 text-slate-500 shadow-sm ring-1 ring-slate-300 transition hover:bg-slate-100 hover:text-slate-950 focus:bg-slate-100 focus:text-slate-950 focus:outline-none focus:ring-2 focus:ring-brand dark:bg-slate-800/95 dark:text-slate-400 dark:ring-slate-700 dark:hover:bg-slate-700 dark:hover:text-white dark:focus:bg-slate-700 dark:focus:text-white',
              conversation.is_archived && 'text-brand dark:text-brand-light',
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
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setMobileMenuOpen((open) => !open);
        }}
        className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-md bg-white/95 text-slate-500 shadow-sm ring-1 ring-slate-300 md:hidden dark:bg-slate-800/95 dark:text-slate-400 dark:ring-slate-700"
        aria-label="会话更多操作"
        aria-expanded={mobileMenuOpen}
      >
        <MoreHorizontal className="h-3.5 w-3.5" />
      </button>
      {mobileMenuOpen && (
        <div className="absolute right-2 top-10 z-20 min-w-32 rounded-md border border-slate-300 bg-white p-1 shadow-xl dark:border-slate-700 dark:bg-slate-900 md:hidden">
          {onTogglePin && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                setMobileMenuOpen(false);
                onTogglePin();
              }}
              className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <Pin className="h-3.5 w-3.5" />
              {conversation.is_pinned ? '取消置顶' : '置顶会话'}
            </button>
          )}
          {onToggleArchive && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                setMobileMenuOpen(false);
                onToggleArchive();
              }}
              className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              {conversation.is_archived ? <ArchiveRestore className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}
              {conversation.is_archived ? '取消归档' : '归档会话'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
