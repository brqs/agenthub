import { AtSign, Paperclip, Send } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { AgentMentionPicker } from './AgentMentionPicker';
import { DemoPromptBar } from './DemoPromptBar';
import type { DemoConversation } from '@/lib/mockData';
import type { Agent } from '@/lib/types';

export interface MentionInsertRequest {
  agentId: string;
  requestId: number;
}

export function MessageInput({
  conversation,
  onSend,
  isSending = false,
  agents = [],
  mentionInsertRequest = null,
}: {
  conversation: DemoConversation;
  onSend: (text: string) => void;
  isSending?: boolean;
  agents?: Agent[];
  mentionInsertRequest?: MentionInsertRequest | null;
}) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const handledMentionRequestId = useRef<number | null>(null);
  const mentionQuery = useMemo(() => {
    if (conversation.mode !== 'group') return null;
    const match = text.match(/@([\w-]*)$/);
    return match?.[1] ?? null;
  }, [conversation.mode, text]);
  const availableAgents = agents.filter((agent) => conversation.agent_ids.includes(agent.id));

  function submit() {
    const value = text.trim();
    if (!value || isSending) return;
    onSend(value);
    setText('');
  }

  useEffect(() => {
    if (!mentionInsertRequest || conversation.mode !== 'group') return;
    if (handledMentionRequestId.current === mentionInsertRequest.requestId) return;
    handledMentionRequestId.current = mentionInsertRequest.requestId;

    const mention = `@${mentionInsertRequest.agentId}`;
    const textarea = textareaRef.current;
    const selectionStart = textarea?.selectionStart ?? text.length;
    const selectionEnd = textarea?.selectionEnd ?? selectionStart;
    const prefix = selectionStart > 0 && !/\s/.test(text[selectionStart - 1] ?? '') ? ' ' : '';
    const suffix =
      selectionEnd < text.length && !/\s/.test(text[selectionEnd] ?? '') ? ' ' : ' ';
    const insertedText = `${prefix}${mention}${suffix}`;
    const nextText = `${text.slice(0, selectionStart)}${insertedText}${text.slice(selectionEnd)}`;
    const nextCaret = selectionStart + insertedText.length;

    setText(nextText);
    window.requestAnimationFrame(() => {
      textarea?.focus();
      textarea?.setSelectionRange(nextCaret, nextCaret);
    });
  }, [conversation.mode, mentionInsertRequest, text]);

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  function pickAgent(agent: Agent) {
    setText((current) => current.replace(/@[\w-]*$/, `@${agent.id} `));
  }

  return (
    <footer className="shrink-0 border-t border-slate-800 bg-slate-950 px-5 py-3 max-[800px]:py-2 [@media(max-height:800px)]:py-2">
      {conversation.mode === 'group' && (
        <>
          <DemoPromptBar onSelect={setText} />
          <div className="mb-2 flex items-center gap-2 text-xs text-slate-500 max-[800px]:hidden [@media(max-height:800px)]:hidden">
            <AtSign className="h-3.5 w-3.5" />
            输入 @ 可指定 Agent，默认由 Orchestrator 协调
          </div>
        </>
      )}
      {mentionQuery !== null && (
        <AgentMentionPicker agents={availableAgents} query={mentionQuery} onPick={pickAgent} />
      )}
      <div className="flex items-end gap-3 rounded-md border border-slate-800 bg-slate-900 p-2.5 focus-within:border-brand [@media(max-height:800px)]:p-2">
        <button
          type="button"
          className="rounded-md p-2 text-slate-500 hover:bg-slate-800 hover:text-white"
          title="添加附件"
          aria-label="添加附件"
        >
          <Paperclip className="h-4 w-4" />
        </button>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={isSending}
          placeholder={`发消息到 ${conversation.title}`}
          className="max-h-28 min-h-9 flex-1 resize-none bg-transparent py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 disabled:cursor-not-allowed disabled:opacity-60 [@media(max-height:800px)]:min-h-8 [@media(max-height:800px)]:py-1.5"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!text.trim() || isSending}
          className="flex h-10 w-10 items-center justify-center rounded-md bg-brand text-white transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-40"
          title="发送"
          aria-label="发送"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    </footer>
  );
}
