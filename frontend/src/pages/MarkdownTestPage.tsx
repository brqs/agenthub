import { ScrollText } from 'lucide-react';
import { MessageBubble } from '@/components/chat/MessageBubble';
import { markdownQaMessages } from '@/lib/mockData';

export function MarkdownTestPage() {
  return (
    <div className="flex h-full flex-col bg-slate-950 text-slate-100">
      <header className="flex min-h-[76px] items-center justify-between border-b border-slate-800 px-7">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-light">
            <ScrollText className="h-3.5 w-3.5" />
            Markdown QA Chat
          </div>
          <h1 className="mt-2 truncate text-xl font-semibold text-white">Markdown / Formula 对话渲染测试</h1>
          <p className="mt-1 text-sm text-slate-500">模拟真实聊天消息流，覆盖 Markdown、GFM、KaTeX 和长内容。</p>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-400">
          {markdownQaMessages.length} messages
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-6 py-5 scrollbar-thin">
        <div className="mx-auto flex max-w-5xl flex-col gap-4">
          {markdownQaMessages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
        </div>
      </main>
    </div>
  );
}
