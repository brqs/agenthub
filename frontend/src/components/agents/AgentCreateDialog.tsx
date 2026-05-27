import { X } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { CreateAgentInput } from '@/stores/agentStore';
import type { CreatableAgentProvider } from '@/lib/types';

const DEFAULT_CAPABILITIES = ['需求分析', '代码生成', '测试补齐'];
const DEFAULT_MODELS: Record<CreatableAgentProvider, string> = {
  builtin: 'deepseek',
  claude_code: 'claude-sonnet-4-6',
  codex: 'gpt-4o',
  opencode: 'opencode',
};

const PROVIDER_LABELS: Record<CreatableAgentProvider, string> = {
  builtin: 'Builtin Agent',
  claude_code: 'Claude Code',
  codex: 'Codex',
  opencode: 'OpenCode',
};

function parseJsonRecord(value: string): Record<string, unknown> | null {
  if (!value.trim()) return {};
  try {
    const parsed: unknown = JSON.parse(value);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
}

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
  const [provider, setProvider] = useState<CreatableAgentProvider>('builtin');
  const [model, setModel] = useState(DEFAULT_MODELS.builtin);
  const [command, setCommand] = useState(DEFAULT_MODELS.opencode);
  const [args, setArgs] = useState('');
  const [sdkOptions, setSdkOptions] = useState('{\n  "permissionMode": "default"\n}');
  const [sdkOptionsError, setSdkOptionsError] = useState('');
  const [maxIterations, setMaxIterations] = useState(10);
  const [timeoutSeconds, setTimeoutSeconds] = useState(120);
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
    const parsedSdkOptions = provider === 'claude_code' ? parseJsonRecord(sdkOptions) : undefined;
    if (provider === 'claude_code' && parsedSdkOptions === null) {
      setSdkOptionsError('请输入 JSON 对象');
      return;
    }
    const normalizedSdkOptions = parsedSdkOptions ?? undefined;
    setSdkOptionsError('');
    onCreate({
      name,
      provider,
      model,
      command: command.trim() || undefined,
      args: args.split(/\s+/).map((item) => item.trim()).filter(Boolean),
      sdkOptions: normalizedSdkOptions,
      maxIterations,
      timeoutSeconds,
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
            <p className="mt-1 text-xs text-slate-500">填写名称、Provider、模型和提示词。</p>
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
              <span id="agent-provider-label" className="text-xs font-medium text-slate-400">Provider</span>
              <select
                aria-labelledby="agent-provider-label"
                value={provider}
                onChange={(event) => {
                  const nextProvider = event.target.value as CreatableAgentProvider;
                  setProvider(nextProvider);
                  setModel(DEFAULT_MODELS[nextProvider]);
                  if (nextProvider === 'opencode') setCommand(DEFAULT_MODELS.opencode);
                }}
                className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
              >
                {Object.entries(PROVIDER_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            {provider === 'opencode' ? (
              <label className="block">
                <span className="text-xs font-medium text-slate-400">Command</span>
                <input
                  value={command}
                  onChange={(event) => setCommand(event.target.value)}
                  className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
                />
              </label>
            ) : (
              <label className="block">
                <span className="text-xs font-medium text-slate-400">
                  {provider === 'builtin' ? 'Model Backend' : '模型'}
                </span>
                <input
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
                />
              </label>
            )}
          </div>

          {provider === 'builtin' && (
            <label className="block">
              <span className="text-xs font-medium text-slate-400">Max Iterations</span>
              <input
                type="number"
                min={1}
                max={50}
                value={maxIterations}
                onChange={(event) => setMaxIterations(Number(event.target.value))}
                className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
              />
            </label>
          )}

          {provider === 'opencode' && (
            <label className="block">
              <span className="text-xs font-medium text-slate-400">Args</span>
              <input
                value={args}
                onChange={(event) => setArgs(event.target.value)}
                placeholder="用空格分隔，例如 run --json"
                className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
              />
            </label>
          )}

          {provider === 'claude_code' && (
            <label className="block">
              <span className="text-xs font-medium text-slate-400">SDK Options JSON</span>
              <textarea
                aria-label="SDK Options JSON"
                value={sdkOptions}
                onChange={(event) => setSdkOptions(event.target.value)}
                rows={4}
                className="mt-2 w-full resize-none rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs leading-5 text-slate-100 outline-none focus:border-brand"
              />
              {sdkOptionsError && (
                <span className="mt-1 block text-xs text-rose-300">{sdkOptionsError}</span>
              )}
            </label>
          )}

          {provider !== 'builtin' && (
            <label className="block">
              <span className="text-xs font-medium text-slate-400">Timeout Seconds</span>
              <input
                type="number"
                min={10}
                max={600}
                value={timeoutSeconds}
                onChange={(event) => setTimeoutSeconds(Number(event.target.value))}
                className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
              />
            </label>
          )}

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
