import { Archive, ArchiveRestore } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { ConversationItem } from '@/components/conversation/ConversationItem';
import { useConversations } from '@/hooks/useConversations';
import { useUpdateConversation } from '@/hooks/useUpdateConversation';
import { useChatStore } from '@/stores/chatStore';

export function ArchivePage() {
  const navigate = useNavigate();
  const { data: conversations, isLoading } = useConversations({ archived: true });
  const selectedConversationId = useChatStore((state) => state.selectedConversationId);
  const setSelectedConversationId = useChatStore((state) => state.setSelectedConversationId);
  const updateConversation = useUpdateConversation();
  const archived = conversations.filter((conversation) => conversation.is_archived);

  function openConversation(conversationId: string) {
    setSelectedConversationId(conversationId);
    navigate(`/chat/${conversationId}`);
  }

  return (
    <div className="flex h-full flex-col bg-slate-100 dark:bg-slate-950">
      <header className="flex min-h-[68px] items-center justify-between border-b border-slate-200 px-4 dark:border-slate-800 sm:min-h-[76px] sm:px-8">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-light">
            <Archive className="h-3.5 w-3.5" />
            Archive
          </div>
          <h1 className="mt-2 text-xl font-semibold text-slate-950 dark:text-white">归档会话</h1>
        </div>
        <div className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          {archived.length} 个会话
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto p-4 scrollbar-thin sm:p-8">
        {isLoading ? (
          <div className="flex min-h-full items-center justify-center text-sm text-slate-500">
            正在加载归档会话
          </div>
        ) : archived.length ? (
          <div className="mx-auto max-w-3xl space-y-2">
            {archived.map((conversation) => (
              <ConversationItem
                key={conversation.id}
                conversation={conversation}
                active={conversation.id === selectedConversationId}
                onSelect={() => openConversation(conversation.id)}
                onTogglePin={() =>
                  updateConversation.update(conversation.id, {
                    is_pinned: !conversation.is_pinned,
                  })
                }
                onToggleArchive={() =>
                  updateConversation.update(conversation.id, {
                    is_archived: !conversation.is_archived,
                  })
                }
              />
            ))}
          </div>
        ) : (
          <div className="flex min-h-full items-center justify-center">
            <div className="max-w-sm rounded-md border border-dashed border-slate-300 bg-white/70 p-8 text-center dark:border-slate-800 dark:bg-slate-900/50">
              <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-md bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                <ArchiveRestore className="h-5 w-5" />
              </div>
              <h2 className="mt-4 text-sm font-semibold text-slate-950 dark:text-white">
                暂无归档会话
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-500">
                在聊天列表中归档会话后，会在这里集中查看和恢复。
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
