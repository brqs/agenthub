import { AtSign, Paperclip, Send, Slash } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { AgentMentionPicker } from './AgentMentionPicker';
import type { DemoConversation } from '@/lib/mockData';
import type { Agent } from '@/lib/types';

export interface MentionInsertRequest {
  agentId: string;
  requestId: number;
}

const slashCommands = [
  {
    value: '/grill-me',
    label: '/grill-me',
    description: '开始需求追问，先锁定关键规格',
  },
  {
    value: '/grill-with-docs',
    label: '/grill-with-docs',
    description: '结合 Workspace 文档澄清术语',
  },
  {
    value: '/setup-matt-pocock-skills',
    label: '/setup-matt-pocock-skills',
    description: '初始化本会话 Workspace 协作文档',
  },
];

export function MessageInput({
  conversation,
  onSend,
  isSending = false,
  isOffline = false,
  agents = [],
  mentionInsertRequest = null,
}: {
  conversation: DemoConversation;
  onSend: (text: string) => void | Promise<void>;
  isSending?: boolean;
  isOffline?: boolean;
  agents?: Agent[];
  mentionInsertRequest?: MentionInsertRequest | null;
}) {
  const [text, setText] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const handledMentionRequestId = useRef<number | null>(null);
  const mentionQuery = useMemo(() => {
    if (conversation.mode !== 'group') return null;
    const match = text.match(/@([\w-]*)$/);
    return match?.[1] ?? null;
  }, [conversation.mode, text]);
  const slashMatches = useMemo(() => {
    const trimmed = text.trimStart();
    if (!trimmed.startsWith('/')) return [];
    const query = trimmed.slice(1).toLowerCase();
    return slashCommands.filter((command) =>
      command.value.slice(1).toLowerCase().startsWith(query),
    );
  }, [text]);
  const availableAgents = agents.filter((agent) => conversation.agent_ids.includes(agent.id));
  const isUnavailable = isSending || isOffline;

  async function submit() {
    const value = text.trim();
    if (!value || isUnavailable) return;
    setSubmitError(null);
    try {
      await onSend(value);
      setText('');
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : String(error));
    }
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

  useEffect(() => {
    function handleFillMessageInput(event: Event) {
      const detail = (event as CustomEvent<{ text?: unknown }>).detail;
      if (typeof detail?.text !== 'string' || !detail.text.trim()) return;
      const nextText = detail.text;
      setText(nextText);
      setSubmitError(null);
      window.requestAnimationFrame(() => {
        textareaRef.current?.focus();
        const nextCaret = nextText.length;
        textareaRef.current?.setSelectionRange(nextCaret, nextCaret);
      });
    }

    window.addEventListener('agenthub:fill-message-input', handleFillMessageInput);
    return () => {
      window.removeEventListener('agenthub:fill-message-input', handleFillMessageInput);
    };
  }, []);

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  function pickAgent(agent: Agent) {
    setText((current) => current.replace(/@[\w-]*$/, `@${agent.id} `));
  }

  function pickSlashCommand(command: (typeof slashCommands)[number]) {
    setText(`${command.value} `);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  return (
    <footer className="min-w-0 max-w-full shrink-0 overflow-hidden border-t border-slate-200 bg-slate-100 px-3 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-2 dark:border-slate-800 dark:bg-slate-950 sm:px-5 sm:py-3 max-[800px]:py-2 [@media(max-height:800px)]:py-2">
      {conversation.mode === 'group' && (
        <div className="mb-2 flex items-center gap-2 text-xs text-slate-500 max-[800px]:hidden [@media(max-height:800px)]:hidden">
          <AtSign className="h-3.5 w-3.5" />
          输入 @ 可指定 Agent，默认由 Orchestrator 协调
        </div>
      )}
      {mentionQuery !== null && (
        <AgentMentionPicker agents={availableAgents} query={mentionQuery} onPick={pickAgent} />
      )}
      {slashMatches.length > 0 && (
        <div className="mb-2 overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg dark:border-slate-800 dark:bg-slate-900">
          {slashMatches.map((command) => (
            <button
              key={command.value}
              type="button"
              onClick={() => pickSlashCommand(command)}
              className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <Slash className="h-4 w-4 shrink-0 text-brand" />
              <span className="min-w-0">
                <span className="block font-medium text-slate-900 dark:text-slate-100">
                  {command.label}
                </span>
                <span className="block truncate text-xs text-slate-500 dark:text-slate-400">
                  {command.description}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
      {isOffline && (
        <p className="mb-2 text-xs font-medium text-amber-700 dark:text-amber-300">
          当前离线，恢复网络后可继续发送
        </p>
      )}
      {submitError && (
        <p className="mobile-text-safe mb-2 text-xs font-medium text-red-600 dark:text-red-400">
          {submitError}
        </p>
      )}
      <div className="flex min-w-0 max-w-full items-end gap-2 rounded-md border border-slate-300 bg-white p-2.5 focus-within:border-brand dark:border-slate-800 dark:bg-slate-900 sm:gap-3 [@media(max-height:800px)]:p-2">
        <button
          type="button"
          className="shrink-0 rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
          title="添加附件"
          aria-label="添加附件"
        >
          <Paperclip className="h-4 w-4" />
        </button>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            if (submitError) setSubmitError(null);
          }}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={isUnavailable}
          placeholder={isOffline ? '当前离线，恢复网络后可继续发送' : `发消息到 ${conversation.title}`}
          className="mobile-text-safe max-h-28 min-h-9 min-w-0 flex-1 resize-none bg-transparent py-2 text-base text-slate-950 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed disabled:opacity-60 dark:text-slate-100 dark:placeholder:text-slate-600 sm:text-sm [@media(max-height:800px)]:min-h-8 [@media(max-height:800px)]:py-1.5"
        />
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!text.trim() || isUnavailable}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-brand text-white transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-40"
          title="发送"
          aria-label="发送"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    </footer>
  );
}
