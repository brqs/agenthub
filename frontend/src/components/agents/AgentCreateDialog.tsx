import { X } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { CreateAgentInput } from '@/stores/agentStore';
import type { Agent } from '@/lib/types';

const DEFAULT_CAPABILITIES = ['需求分析', '代码生成', '测试补齐'];

export function AgentCreateDialog({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (input: CreateAgentInput) => void;
}) {
  const [name, setName] = useState('Frontend Reviewer');
  // Default to `claude` (real backend rejects `custom` without `upstream_provider`,
  // which is currently not in the OpenAPI). Mock mode accepts either.
  const [provider, setProvider] = useState<Agent['provider']>('claude');
  const [model, setModel] = useState('claude-sonnet-4-6');
  const [capabilities, setCapabilities] = useState(DEFAULT_CAPABILITIES.join(', '));
  const [systemPrompt, setSystemPrompt] = useState('你负责审查前端交互、视觉一致性和可演示性。');

  const parsedCapabilities = useMemo(
    () =>
      capabilities
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
    [capabilities],
  );

  if (!open) return null;

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    onCreate({
      name,
      provider,
      model,
      capabilities: parsedCapabilities.length ? parsedCapabilities : DEFAULT_CAPABILITIES,
      systemPrompt,
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 backdrop-blur-sm">
      <form
        onSubmit={submit}
        className="w-full max-w-xl overflow-hidden rounded-md border border-slate-700 bg-slate-900 shadow-2xl shadow-black/40"
      >
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-white">创建 Agent</h2>
            <p className="mt-1 text-xs text-slate-500">Mock 创建，后续会接入真实 Agent API。</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-2 text-slate-500 hover:bg-slate-800 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-5">
          <label className="block">
            <span className="text-xs font-medium text-slate-400">名称</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
            />
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="text-xs font-medium text-slate-400">Provider</span>
              <select
                value={provider}
                onChange={(event) => setProvider(event.target.value as Agent['provider'])}
                className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
              >
                <option value="custom">custom</option>
                <option value="deepseek">deepseek</option>
                <option value="openai">openai</option>
                <option value="claude">claude</option>
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-400">模型</span>
              <input
                value={model}
                onChange={(event) => setModel(event.target.value)}
                className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
              />
            </label>
          </div>

          <label className="block">
            <span className="text-xs font-medium text-slate-400">能力标签</span>
            <input
              value={capabilities}
              onChange={(event) => setCapabilities(event.target.value)}
              className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium text-slate-400">System Prompt</span>
            <textarea
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.target.value)}
              rows={4}
              className="mt-2 w-full resize-none rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm leading-6 text-slate-100 outline-none focus:border-brand"
            />
          </label>
        </div>

        <div className="flex justify-end gap-3 border-t border-slate-800 px-5 py-4">
          <button type="button" onClick={onClose} className="rounded-md px-4 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-white">
            取消
          </button>
          <button type="submit" className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover">
            创建
          </button>
        </div>
      </form>
    </div>
  );
}
