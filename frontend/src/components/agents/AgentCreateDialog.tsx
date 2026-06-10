import {
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  FileText,
  Sparkles,
  UploadCloud,
  X,
} from 'lucide-react';
import { useMemo, useRef, useState, type FormEvent } from 'react';
import { cn } from '@/lib/utils';
import type {
  AgentWrapperProfile,
  CreateAgentInput,
  ServerBaseAgentId,
} from '@/stores/agentStore';

const STEP_IDS = ['base', 'profile', 'skills', 'review'] as const;
type StepId = (typeof STEP_IDS)[number];

const STEP_LABELS: Record<StepId, string> = {
  base: '底座',
  profile: '传递字段',
  skills: 'Skills',
  review: '确认',
};

const BASE_AGENTS: Array<{
  id: ServerBaseAgentId;
  provider: CreateAgentInput['provider'];
  name: string;
  summary: string;
  defaultCapabilities: string[];
  defaultStrengths: string[];
  defaultWeaknesses: string[];
  defaultTaskTypes: string[];
}> = [
  {
    id: 'claude-code',
    provider: 'claude_code',
    name: 'Claude Code',
    summary: '适合代码实现、文件编辑、修复和代码审查。',
    defaultCapabilities: ['代码实现', '文件编辑', '调试修复'],
    defaultStrengths: ['明确子任务实现', '跨文件修改', '修复报错', '代码审查'],
    defaultWeaknesses: ['全局产品规划需要 Orchestrator 先拆解'],
    defaultTaskTypes: ['实现', '修复', '审查'],
  },
  {
    id: 'codex-helper',
    provider: 'codex',
    name: 'Codex Helper',
    summary: '适合复杂任务拆解、架构判断、兜底排查和最终复核。',
    defaultCapabilities: ['仓库理解', '架构分析', '复杂排查'],
    defaultStrengths: ['任务规划', '架构权衡', '代码审阅', '疑难问题排查'],
    defaultWeaknesses: ['简单重复实现不应优先交给它'],
    defaultTaskTypes: ['规划', '架构', '审查', '兜底修复'],
  },
  {
    id: 'opencode-helper',
    provider: 'opencode',
    name: 'OpenCode Helper',
    summary: '适合 CLI 驱动的实现、文件修改、验证和并行开发。',
    defaultCapabilities: ['CLI 工作流', '文件修改', '验证'],
    defaultStrengths: ['快速实现', '命令行验证', '静态产物生成', '修复迭代'],
    defaultWeaknesses: ['全局架构取舍需要 Orchestrator 明确边界'],
    defaultTaskTypes: ['实现', '验证', '修复'],
  },
];

function textToList(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function listToText(value: string[]): string {
  return value.join('\n');
}

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function buildSystemPrompt(input: {
  role: string;
  purpose: string;
  outputStyle: string;
  boundaries: string[];
}): string {
  return [
    input.role ? `角色：${input.role}` : '',
    input.purpose ? `用途：${input.purpose}` : '',
    input.outputStyle ? `输出风格：${input.outputStyle}` : '',
    input.boundaries.length
      ? `边界：\n${input.boundaries.map((item) => `- ${item}`).join('\n')}`
      : '',
  ]
    .filter(Boolean)
    .join('\n\n');
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
  const skillInputRef = useRef<HTMLInputElement | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [baseAgentId, setBaseAgentId] = useState<ServerBaseAgentId | null>(null);
  const [name, setName] = useState('');
  const [purpose, setPurpose] = useState('');
  const [role, setRole] = useState('');
  const [planningProfile, setPlanningProfile] = useState('');
  const [capabilitiesText, setCapabilitiesText] = useState('');
  const [strengthsText, setStrengthsText] = useState('');
  const [weaknessesText, setWeaknessesText] = useState('');
  const [taskTypesText, setTaskTypesText] = useState('');
  const [outputStyle, setOutputStyle] = useState('');
  const [boundariesText, setBoundariesText] = useState('');
  const [skillFiles, setSkillFiles] = useState<File[]>([]);
  const [error, setError] = useState('');

  const step = STEP_IDS[stepIndex] ?? 'base';
  const baseAgent = BASE_AGENTS.find((agent) => agent.id === baseAgentId) ?? null;

  const wrapperProfile: AgentWrapperProfile = useMemo(
    () => ({
      role: role.trim() || null,
      purpose: purpose.trim() || null,
      planning_profile: planningProfile.trim() || null,
      planning_strengths: textToList(strengthsText),
      planning_weaknesses: textToList(weaknessesText),
      preferred_task_types: textToList(taskTypesText),
      capabilities: textToList(capabilitiesText),
      output_style: outputStyle.trim() || null,
      boundaries: textToList(boundariesText),
    }),
    [
      boundariesText,
      capabilitiesText,
      outputStyle,
      planningProfile,
      purpose,
      role,
      strengthsText,
      taskTypesText,
      weaknessesText,
    ],
  );

  const systemPrompt = useMemo(
    () =>
      buildSystemPrompt({
        role,
        purpose,
        outputStyle,
        boundaries: textToList(boundariesText),
      }),
    [boundariesText, outputStyle, purpose, role],
  );

  if (!open) return null;

  function applyBaseAgent(nextBaseAgentId: ServerBaseAgentId) {
    const nextBase = BASE_AGENTS.find((agent) => agent.id === nextBaseAgentId);
    if (!nextBase) return;
    setBaseAgentId(nextBase.id);
    if (!capabilitiesText.trim()) setCapabilitiesText(listToText(nextBase.defaultCapabilities));
    if (!strengthsText.trim()) setStrengthsText(listToText(nextBase.defaultStrengths));
    if (!weaknessesText.trim()) setWeaknessesText(listToText(nextBase.defaultWeaknesses));
    if (!taskTypesText.trim()) setTaskTypesText(listToText(nextBase.defaultTaskTypes));
  }

  function addSkillFiles(files: FileList | null) {
    const nextFiles = Array.from(files ?? []).filter((file) =>
      /\.(md|markdown)$/i.test(file.name),
    );
    setSkillFiles((current) => {
      const byKey = new Map(current.map((file) => [`${file.name}:${file.size}`, file]));
      for (const file of nextFiles) {
        byKey.set(`${file.name}:${file.size}`, file);
      }
      return Array.from(byKey.values());
    });
    if (skillInputRef.current) skillInputRef.current.value = '';
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!baseAgent) {
      setError('请先选择一个服务器底座 Agent。');
      setStepIndex(0);
      return;
    }
    if (!name.trim()) {
      setError('请填写 Agent 名称。');
      setStepIndex(1);
      return;
    }
    if (!purpose.trim() || !planningProfile.trim()) {
      setError('请补充用途和调度描述，这会决定 Orchestrator 什么时候调用它。');
      setStepIndex(1);
      return;
    }
    setError('');
    onCreate({
      name: name.trim(),
      provider: baseAgent.provider,
      baseAgentId: baseAgent.id,
      capabilities: wrapperProfile.capabilities,
      systemPrompt,
      wrapperProfile,
      skillFiles,
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 sm:px-4 sm:py-6 backdrop-blur-sm">
      <form
        onSubmit={submit}
        className="flex h-[100dvh] w-full max-w-5xl flex-col overflow-hidden border border-slate-300 bg-white shadow-2xl shadow-black/20 dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/40 sm:max-h-[calc(100dvh-3rem)] sm:rounded-md"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand dark:text-brand-light">
              <Sparkles className="h-3.5 w-3.5" />
              自定义 Agent 构建器
            </div>
            <h2 className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">
              创建服务器 Agent 套壳
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
            aria-label="关闭"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 md:grid-cols-[220px_minmax(0,1fr)_320px]">
          <nav className="hidden border-r border-slate-200 p-4 dark:border-slate-800 md:block">
            <div className="space-y-2">
              {STEP_IDS.map((id, index) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setStepIndex(index)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-md px-4 py-2 text-left text-sm transition',
                    step === id
                      ? 'bg-brand text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700',
                  )}
                >
                  <span>{index + 1}</span>
                  <span>{STEP_LABELS[id]}</span>
                </button>
              ))}
            </div>
          </nav>

          <main className="min-h-0 overflow-y-auto p-5">
            {error ? (
              <div className="mb-4 rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
                {error}
              </div>
            ) : null}

            {step === 'base' && (
              <section>
                <h3 className="text-base font-semibold text-slate-950 dark:text-white">
                  选择服务器底座 Agent
                </h3>
                <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-500">
                  自定义 Agent 会复用服务器已有的 Codex、OpenCode 或 Claude Code 执行能力。你只需要定义它在调度时的角色、擅长范围和 Skills。
                </p>
                <div className="mt-5 grid gap-3">
                  {BASE_AGENTS.map((agent) => (
                    <button
                      key={agent.id}
                      type="button"
                      onClick={() => applyBaseAgent(agent.id)}
                      className={cn(
                        'rounded-md border p-4 text-left transition',
                        baseAgentId === agent.id
                          ? 'border-brand bg-brand/10'
                          : 'border-slate-300 bg-slate-50 hover:border-slate-400 dark:border-slate-800 dark:bg-slate-950/60 dark:hover:border-slate-700',
                      )}
                    >
                      <div className="flex items-center gap-2 text-sm font-semibold text-slate-950 dark:text-white">
                        <Bot className="h-4 w-4 text-brand dark:text-brand-light" />
                        {agent.name}
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-500">
                        {agent.summary}
                      </p>
                    </button>
                  ))}
                </div>
              </section>
            )}

            {step === 'profile' && (
              <section className="space-y-4">
                <h3 className="text-base font-semibold text-slate-950 dark:text-white">
                  配置传递字段
                </h3>
                <Field label="名称" value={name} onChange={setName} />
                <TextArea label="一句话用途" value={purpose} onChange={setPurpose} rows={2} />
                <TextArea label="角色" value={role} onChange={setRole} rows={2} />
                <TextArea
                  label="调度描述"
                  value={planningProfile}
                  onChange={setPlanningProfile}
                  rows={4}
                  hint="告诉 Orchestrator：什么情况下应该把任务交给这个 Agent。"
                />
                <TextArea
                  label="擅长什么"
                  value={strengthsText}
                  onChange={setStrengthsText}
                  rows={3}
                  hint="每行一个，也可以用逗号分隔。"
                />
                <TextArea
                  label="不擅长什么"
                  value={weaknessesText}
                  onChange={setWeaknessesText}
                  rows={3}
                />
                <TextArea
                  label="适合任务类型"
                  value={taskTypesText}
                  onChange={setTaskTypesText}
                  rows={2}
                />
                <TextArea
                  label="能力标签"
                  value={capabilitiesText}
                  onChange={setCapabilitiesText}
                  rows={2}
                />
                <TextArea
                  label="输出风格"
                  value={outputStyle}
                  onChange={setOutputStyle}
                  rows={2}
                />
                <TextArea
                  label="边界"
                  value={boundariesText}
                  onChange={setBoundariesText}
                  rows={3}
                />
              </section>
            )}

            {step === 'skills' && (
              <section>
                <h3 className="text-base font-semibold text-slate-950 dark:text-white">Skills</h3>
                <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-500">
                  Skill 是可复用的能力说明，支持 .md、.markdown 或 SKILL.md。创建后也可以在 Agent 详情页继续增删改。
                </p>
                <input
                  ref={skillInputRef}
                  type="file"
                  accept=".md,.markdown,text/markdown"
                  multiple
                  className="hidden"
                  onChange={(event) => addSkillFiles(event.currentTarget.files)}
                />
                <button
                  type="button"
                  onClick={() => skillInputRef.current?.click()}
                  className="mt-5 inline-flex items-center gap-2 rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  <UploadCloud className="h-4 w-4" />
                  选择 Skill 文件
                </button>
                <div className="mt-4 space-y-2">
                  {skillFiles.length ? (
                    skillFiles.map((file) => (
                      <div
                        key={`${file.name}:${file.size}`}
                        className="flex items-center justify-between gap-3 rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/60"
                      >
                        <span className="min-w-0 truncate text-slate-800 dark:text-slate-200">
                          {file.name}
                        </span>
                        <span className="shrink-0 text-xs text-slate-500">{fileSize(file.size)}</span>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-md border border-dashed border-slate-300 px-3 py-6 text-center text-sm text-slate-600 dark:border-slate-800 dark:text-slate-500">
                      暂未选择 Skill。可以先创建 Agent，之后再上传。
                    </div>
                  )}
                </div>
              </section>
            )}

            {step === 'review' && (
              <section>
                <h3 className="text-base font-semibold text-slate-950 dark:text-white">
                  确认创建
                </h3>
                <dl className="mt-5 space-y-4 rounded-md border border-slate-300 bg-slate-50 p-4 text-sm dark:border-slate-800 dark:bg-slate-950/60">
                  <SummaryRow label="底座" value={baseAgent?.name ?? '未选择'} />
                  <SummaryRow label="名称" value={name || '未填写'} />
                  <SummaryRow label="用途" value={purpose || '未填写'} />
                  <SummaryRow label="调度描述" value={planningProfile || '未填写'} />
                  <SummaryRow label="Skills" value={`${skillFiles.length} 个待导入`} />
                </dl>
              </section>
            )}
          </main>

          <aside className="hidden min-h-0 border-l border-slate-200 p-4 dark:border-slate-800 md:block">
            <div className="rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
                <FileText className="h-4 w-4 text-brand dark:text-brand-light" />
                预览
              </div>
              <div className="mt-4 text-sm font-semibold text-slate-950 dark:text-white">
                {name || '新 Agent'}
              </div>
              <div className="mt-1 text-xs text-slate-600 dark:text-slate-500">
                套壳自：{baseAgent?.name ?? '未选择底座'}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {wrapperProfile.capabilities.map((capability) => (
                  <span
                    key={capability}
                    className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                  >
                    {capability}
                  </span>
                ))}
              </div>
              <pre className="mt-4 max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-slate-300 bg-white p-3 text-xs leading-5 text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                {systemPrompt ||
                  '填写传递字段后，这里会展示注入给底座 Agent 的个性化说明。'}
              </pre>
            </div>
          </aside>
        </div>

        <div className="flex shrink-0 items-center justify-between gap-3 border-t border-slate-200 px-5 pb-[max(env(safe-area-inset-bottom),1rem)] pt-4 dark:border-slate-800">
          <button
            type="button"
            onClick={() => setStepIndex((index) => Math.max(0, index - 1))}
            disabled={stepIndex === 0}
            className="inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-40 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
          >
            <ChevronLeft className="h-4 w-4" />
            上一步
          </button>
          {stepIndex < STEP_IDS.length - 1 ? (
            <button
              type="button"
              onClick={() => setStepIndex((index) => Math.min(STEP_IDS.length - 1, index + 1))}
              className="inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover"
            >
              下一步
              <ChevronRight className="h-4 w-4" />
            </button>
          ) : (
            <button
              type="submit"
              className="inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover"
            >
              <Check className="h-4 w-4" />
              创建
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-600 dark:text-slate-400">{label}</span>
      <input
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
      />
    </label>
  );
}

function TextArea({
  label,
  value,
  onChange,
  rows,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows: number;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-600 dark:text-slate-400">{label}</span>
      <textarea
        aria-label={label}
        value={value}
        rows={rows}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-6 text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
      />
      {hint ? <span className="mt-1 block text-xs text-slate-500">{hint}</span> : null}
    </label>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-600 dark:text-slate-500">{label}</dt>
      <dd className="mt-1 text-slate-800 dark:text-slate-200">{value}</dd>
    </div>
  );
}
