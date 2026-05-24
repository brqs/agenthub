/**
 * ChatPage — main chat experience.
 *
 * TODO(F):
 *  - 左侧：ConversationList（含新建、置顶、搜索、归档）
 *  - 中间：ChatWindow（消息列表 + 输入框）
 *  - 流式渲染：useStream Hook
 *  - 富媒体块：components/blocks/*
 */

import { useParams } from 'react-router-dom';

export function ChatPage() {
  const { conversationId } = useParams<{ conversationId?: string }>();

  return (
    <div className="flex h-full">
      {/* 侧边栏（占位）*/}
      <aside className="w-72 border-r border-gray-200 dark:border-slate-700 p-4 overflow-y-auto scrollbar-thin">
        <h2 className="text-sm font-semibold text-gray-500 mb-3">会话</h2>
        <div className="text-sm text-gray-400">
          TODO(F): ConversationList
        </div>
      </aside>

      {/* 主聊天区 */}
      <section className="flex-1 flex flex-col">
        {!conversationId ? (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <div className="text-center">
              <div className="text-6xl mb-4">💬</div>
              <p className="text-lg">选择或新建一个会话开始</p>
            </div>
          </div>
        ) : (
          <>
            <header className="border-b border-gray-200 dark:border-slate-700 p-4">
              <h2 className="font-semibold">Conversation {conversationId}</h2>
            </header>
            <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
              <div className="text-sm text-gray-400">TODO(F): MessageList</div>
            </div>
            <footer className="border-t border-gray-200 dark:border-slate-700 p-4">
              <div className="text-sm text-gray-400">TODO(F): MessageInput</div>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}
