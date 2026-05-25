import { AtSign, Paperclip, Send } from 'lucide-react';
import { useState } from 'react';
import type { DemoConversation } from '@/lib/mockData';

export function MessageInput({
  conversation,
  onSend,
}: {
  conversation: DemoConversation;
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState('');

  function submit() {
    const value = text.trim();
    if (!value) return;
    onSend(value);
    setText('');
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <footer className="shrink-0 border-t border-slate-800 bg-slate-950 px-5 py-4">
      {conversation.mode === 'group' && (
        <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
          <AtSign className="h-3.5 w-3.5" />
          输入 @ 可指定 Agent，默认由 Orchestrator 协调
        </div>
      )}
      <div className="flex items-end gap-3 rounded-md border border-slate-800 bg-slate-900 p-3 focus-within:border-brand">
        <button type="button" className="rounded-md p-2 text-slate-500 hover:bg-slate-800 hover:text-white">
          <Paperclip className="h-4 w-4" />
        </button>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder={`发消息到 ${conversation.title}`}
          className="max-h-32 min-h-10 flex-1 resize-none bg-transparent py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!text.trim()}
          className="flex h-10 w-10 items-center justify-center rounded-md bg-brand text-white transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    </footer>
  );
}

