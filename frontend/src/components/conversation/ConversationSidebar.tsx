import { PanelLeftClose, Plus, Search } from 'lucide-react';
import { ConversationItem } from './ConversationItem';
import type { DemoConversation } from '@/lib/mockData';
import { cn } from '@/lib/utils';

export function ConversationSidebar({
  conversations,
  selectedConversationId,
  search,
  onSearch,
  onSelect,
  onNewConversation,
  onCollapse,
  onTogglePin,
  onToggleArchive,
  presentation = 'desktop',
}: {
  conversations: DemoConversation[];
  selectedConversationId: string;
  search: string;
  onSearch: (value: string) => void;
  onSelect: (conversationId: string) => void;
  onNewConversation: () => void;
  onCollapse?: () => void;
  onTogglePin?: (conversationId: string) => void;
  onToggleArchive?: (conversationId: string) => void;
  presentation?: 'desktop' | 'mobile';
}) {
  const normalized = search.trim().toLowerCase();
  const filtered = conversations.filter((conversation) =>
    conversation.title.toLowerCase().includes(normalized),
  );
  const pinned = filtered.filter((conversation) => conversation.is_pinned);
  const recent = filtered.filter((conversation) => !conversation.is_pinned);

  return (
    <aside
      className={cn(
        'h-full shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900',
        presentation === 'desktop' ? 'hidden w-72 md:flex' : 'flex w-full',
      )}
    >
      <div className="px-4 pb-2 pt-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold text-slate-950 dark:text-white">AgentHub</h1>
            <p className="text-xs text-slate-500">多 Agent 协作频道</p>
          </div>
          <div className="flex items-center gap-2">
            {onCollapse && (
              <button
                type="button"
                onClick={onCollapse}
                className="flex h-9 w-9 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-brand dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
                title="收起会话列表"
                aria-label="收起会话列表"
              >
                <PanelLeftClose className="h-4 w-4" />
              </button>
            )}
            <button
              type="button"
              onClick={onNewConversation}
              className="flex h-9 w-9 items-center justify-center rounded-md bg-brand text-white transition hover:bg-brand-hover"
              title="新建会话"
              aria-label="新建会话"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
        </div>
        <label className="mt-4 flex items-center gap-2 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-500 ring-1 ring-slate-300 focus-within:ring-brand dark:bg-slate-950 dark:text-slate-400 dark:ring-slate-800">
          <Search className="h-4 w-4" />
          <input
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="搜索会话"
            className="min-w-0 flex-1 bg-transparent text-slate-950 outline-none placeholder:text-slate-400 dark:text-slate-200 dark:placeholder:text-slate-600"
          />
        </label>
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-3 scrollbar-thin">
        {pinned.length > 0 && (
          <section>
            <h2 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              置顶
            </h2>
            <div className="space-y-1">
              {pinned.map((conversation) => (
                <ConversationItem
                  key={conversation.id}
                  conversation={conversation}
                  active={conversation.id === selectedConversationId}
                  onSelect={() => onSelect(conversation.id)}
                  onTogglePin={() => onTogglePin?.(conversation.id)}
                  onToggleArchive={() => onToggleArchive?.(conversation.id)}
                />
              ))}
            </div>
          </section>
        )}

        <section>
          <h2 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            最近
          </h2>
          <div className="space-y-1">
            {recent.length ? (
              recent.map((conversation) => (
                <ConversationItem
                  key={conversation.id}
                  conversation={conversation}
                  active={conversation.id === selectedConversationId}
                  onSelect={() => onSelect(conversation.id)}
                  onTogglePin={() => onTogglePin?.(conversation.id)}
                  onToggleArchive={() => onToggleArchive?.(conversation.id)}
                />
              ))
            ) : (
              <div className="rounded-md border border-dashed border-slate-300 px-3 py-6 text-center text-sm text-slate-500 dark:border-slate-800">
                {normalized ? '没有匹配的会话' : '暂无最近会话'}
              </div>
            )}
          </div>
        </section>
      </div>
    </aside>
  );
}
