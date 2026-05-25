import { Hash, Pin, Users } from 'lucide-react';
import type { DemoConversation } from '@/lib/mockData';
import { cn, formatTime } from '@/lib/utils';

export function ConversationItem({
  conversation,
  active,
  onSelect,
}: {
  conversation: DemoConversation;
  active: boolean;
  onSelect: () => void;
}) {
  const ModeIcon = conversation.mode === 'group' ? Users : Hash;

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'group w-full rounded-md px-3 py-2 text-left transition',
        active ? 'bg-slate-800 text-white' : 'text-slate-300 hover:bg-slate-800/70 hover:text-white',
      )}
    >
      <div className="flex items-center gap-2">
        <ModeIcon className="h-4 w-4 shrink-0 text-slate-500" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{conversation.title}</span>
        {conversation.is_pinned && <Pin className="h-3.5 w-3.5 shrink-0 text-brand-light" />}
        {conversation.unread_count ? (
          <span className="rounded-full bg-brand px-1.5 text-[10px] font-semibold text-white">
            {conversation.unread_count}
          </span>
        ) : null}
      </div>
      <div className="mt-1 flex items-center gap-2 pl-6 text-xs text-slate-500">
        <span>{conversation.mode === 'group' ? `${conversation.agent_ids.length} Agents` : conversation.agent_ids[0]}</span>
        <span>·</span>
        <span>{formatTime(conversation.last_message_at)}</span>
      </div>
      <p className="mt-1 truncate pl-6 text-xs text-slate-500">
        {conversation.last_message_preview}
      </p>
    </button>
  );
}

