import { X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { Agent, UpdateAgentRequest } from '@/lib/types';

export function AgentEditDialog({
  agent,
  open,
  isPending = false,
  onClose,
  onUpdate,
}: {
  agent: Agent | null;
  open: boolean;
  isPending?: boolean;
  onClose: () => void;
  onUpdate: (agentId: string, input: UpdateAgentRequest) => Promise<void> | void;
}) {
  const [name, setName] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [capabilities, setCapabilities] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');

  useEffect(() => {
    if (!agent) return;
    setName(agent.name);
    setAvatarUrl(agent.avatar_url);
    setCapabilities(agent.capabilities.join(', '));
    setSystemPrompt(agent.system_prompt ?? '');
  }, [agent]);

  const parsedCapabilities = useMemo(
    () =>
      capabilities
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
    [capabilities],
  );

  if (!open || !agent) return null;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agent || !name.trim() || isPending) return;
    await onUpdate(agent.id, {
      name: name.trim(),
      avatar_url: avatarUrl.trim(),
      capabilities: parsedCapabilities,
      system_prompt: systemPrompt.trim() || null,
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 sm:px-4 sm:py-6 backdrop-blur-sm">
      <form
        onSubmit={submit}
        className="flex h-[100dvh] w-full max-w-xl flex-col overflow-hidden border border-slate-300 bg-white shadow-2xl shadow-black/20 dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/40 sm:max-h-[calc(100dvh-3rem)] sm:rounded-md"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div>
            <h2 className="text-base font-semibold text-slate-950 dark:text-white">编辑 Agent</h2>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-500">
              内置 Agent 不可编辑，此处仅用于自建 Agent。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
            title="关闭"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5 scrollbar-thin">
          <label className="block">
            <span className="text-xs font-medium text-slate-600 dark:text-slate-400">名称</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
              Avatar URL
            </span>
            <input
              value={avatarUrl}
              onChange={(event) => setAvatarUrl(event.target.value)}
              className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-slate-600 dark:text-slate-400">能力标签</span>
            <input
              value={capabilities}
              onChange={(event) => setCapabilities(event.target.value)}
              className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
              System Prompt
            </span>
            <textarea
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.target.value)}
              rows={4}
              className="mt-2 w-full resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-6 text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>
        </div>

        <div className="flex shrink-0 justify-end gap-3 border-t border-slate-200 px-5 pb-[max(env(safe-area-inset-bottom),1rem)] pt-4 dark:border-slate-800">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={isPending || !name.trim()}
            className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isPending ? '保存中...' : '保存'}
          </button>
        </div>
      </form>
    </div>
  );
}
