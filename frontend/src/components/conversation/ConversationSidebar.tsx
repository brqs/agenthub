import { Plus, Search } from 'lucide-react';
import { ConversationItem } from './ConversationItem';
import type { DemoConversation } from '@/lib/mockData';

export function ConversationSidebar({
  conversations,
  selectedConversationId,
  search,
  onSearch,
  onSelect,
  onNewConversation,
  onToggleArchive,
}: {
  conversations: DemoConversation[];
  selectedConversationId: string;
  search: string;
  onSearch: (value: string) => void;
  onSelect: (conversationId: string) => void;
  onNewConversation: () => void;
  onToggleArchive?: (conversationId: string) => void;
}) {
  const normalized = search.trim().toLowerCase();
  const filtered = conversations.filter((conversation) =>
    conversation.title.toLowerCase().includes(normalized),
  );
  const pinned = filtered.filter((conversation) => conversation.is_pinned);
  const recent = filtered.filter((conversation) => !conversation.is_pinned);

  return (
    <aside className="flex h-screen w-72 shrink-0 flex-col border-r border-slate-800 bg-slate-900">
      <div className="border-b border-slate-800 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold text-white">AgentHub</h1>
            <p className="text-xs text-slate-500">多 Agent 协作频道</p>
          </div>
          <button
            type="button"
            onClick={onNewConversation}
            className="flex h-9 w-9 items-center justify-center rounded-md bg-brand text-white transition hover:bg-brand-hover"
            title="新建会话"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <label className="mt-4 flex items-center gap-2 rounded-md bg-slate-950 px-3 py-2 text-sm text-slate-400 ring-1 ring-slate-800 focus-within:ring-brand">
          <Search className="h-4 w-4" />
          <input
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="搜索会话"
            className="min-w-0 flex-1 bg-transparent text-slate-200 outline-none placeholder:text-slate-600"
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
                  onToggleArchive={() => onToggleArchive?.(conversation.id)}
                />
              ))
            ) : (
              <div className="rounded-md border border-dashed border-slate-800 px-3 py-6 text-center text-sm text-slate-500">
                {normalized ? '没有匹配的会话' : '暂无最近会话'}
              </div>
            )}
          </div>
        </section>
      </div>
    </aside>
  );
}
