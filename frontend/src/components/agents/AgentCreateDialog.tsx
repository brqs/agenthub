import {
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { useAgentTemplates } from '@/hooks/useAgentTemplates';
import { useModelAccounts, useModelProviders } from '@/hooks/useModelAccounts';
import { extractApiError } from '@/lib/api';
import type {
  AgentBuilderProfile,
  AgentMemoryPolicy,
  AgentModelProfile,
  AgentPermissions,
  AgentTemplate,
  CreatableAgentProvider,
  ModelAccount,
  ModelProvider,
  ModelProviderInfo,
} from '@/lib/types';
import { cn } from '@/lib/utils';
import type { CreateAgentInput } from '@/stores/agentStore';

const STEP_IDS = ['basics', 'behavior', 'permissions', 'publish'] as const;
type StepId = (typeof STEP_IDS)[number];

const STEP_LABELS: Record<StepId, string> = {
  basics: '基础',
  behavior: '行为',
  permissions: '工具',
  publish: '确认',
};

const DEFAULT_PERMISSIONS: AgentPermissions = {
  workspace_read: false,
  workspace_write: false,
  run_commands: 'never',
  network: 'never',
  deploy: 'never',
  external_accounts: 'never',
};

const DEFAULT_PROFILE: AgentBuilderProfile = {
  role: '一个可靠的自定义 Agent。',
  purpose: '帮助用户处理一个明确、可重复的任务。',
  goals: ['行动前先理解用户的真实需求'],
  tone: '清晰、协作、不过度打扰',
  do_not_do: ['未经确认不要执行破坏性操作'],
  clarification_policy: 'balanced',
  output_style: '回答保持简洁，并给出可执行的下一步。',
  starters: ['帮我处理这个任务。'],
};

const FALLBACK_TEMPLATES: AgentTemplate[] = [
  {
    id: 'paper-research-assistant',
    name: '论文资料整理助手',
    description: '整理论文、笔记和阅读摘要，保持谨慎细致的风格。',
    category: 'research',
    capabilities: ['研究', '总结', '写作'],
    builder_profile: {
      role: '一个耐心的研究助手，帮助用户收集和整理论文笔记。',
      purpose: '帮助用户阅读、对比和总结学术资料。',
      goals: ['提取上传笔记中的关键观点和术语', '区分原文内容与生成摘要', '修改用户原文前先询问'],
      tone: '温和、精确、像老师一样解释清楚',
      do_not_do: ['不要编造引用', '未经确认不要改写原文'],
      clarification_policy: 'ask_first',
      output_style: '使用短小分节，并明确标注不确定信息。',
      starters: ['总结这份论文笔记。', '对比这两个论点。', '把这个提纲整理成阅读简报。'],
    },
    permissions: { ...DEFAULT_PERMISSIONS, workspace_read: true },
    memory_policy: 'conversation',
    model_backend: 'deepseek',
  },
  {
    id: 'frontend-designer',
    name: '前端设计助手',
    description: '在当前会话 Workspace 中设计和修改精致的网页界面。',
    category: 'frontend',
    capabilities: ['前端', 'UI', 'Workspace'],
    builder_profile: {
      role: '一个专注于可用性和完成度的前端设计 Agent。',
      purpose: '在 Workspace 中创建和优化静态前端产物。',
      goals: ['按需求产出清晰的 HTML/CSS/JS 文件', '保证桌面端和移动端都能正常使用', '在关键设计取舍处简短说明原因'],
      tone: '直接、协作、关注设计质量',
      do_not_do: ['未经确认不要部署'],
      clarification_policy: 'balanced',
      output_style: '优先给出简洁进展和具体文件产物。',
      starters: ['创建一个落地页原型。', '优化这个组件布局。', '让这个页面适配移动端。'],
    },
    permissions: { ...DEFAULT_PERMISSIONS, workspace_read: true, workspace_write: true },
    memory_policy: 'conversation',
    model_backend: 'deepseek',
  },
  {
    id: 'code-reviewer',
    name: '代码审查助手',
    description: '检查代码改动中的 bug、风险和缺失测试。',
    category: 'engineering',
    capabilities: ['审查', '测试', '质量'],
    builder_profile: {
      role: '一个优先关注正确性和回归风险的代码审查 Agent。',
      purpose: '审查代码改动，并指出可执行的问题。',
      goals: ['先列出具体发现', '引用相关文件和触发场景', '避免空泛或纯风格反馈'],
      tone: '简洁、有经验、偏工程审查',
      do_not_do: ['除非用户要求，否则不要直接重写代码'],
      clarification_policy: 'balanced',
      output_style: '先列问题，再补充剩余风险。',
      starters: ['审查当前改动。', '检查这个组件是否有回归风险。'],
    },
    permissions: { ...DEFAULT_PERMISSIONS, workspace_read: true },
    memory_policy: 'conversation',
    model_backend: 'deepseek',
  },
  {
    id: 'deployment-helper',
    name: '部署助手',
    description: '准备发布说明、检查产物，并引导部署步骤。',
    category: 'deployment',
    capabilities: ['部署', '发布', '诊断'],
    builder_profile: {
      role: '一个负责发布准备和部署诊断的助手。',
      purpose: '帮助用户打包、验证并说明部署是否就绪。',
      goals: ['发布前检查必要产物', '清楚解释部署失败状态', '执行破坏性或外部操作前先确认'],
      tone: '冷静、清晰、偏运维',
      do_not_do: ['未经明确确认不要部署或停止服务'],
      clarification_policy: 'ask_first',
      output_style: '使用短清单和精确命令摘要。',
      starters: ['检查这个 Workspace 是否可以部署。', '准备发布说明。'],
    },
    permissions: { ...DEFAULT_PERMISSIONS, workspace_read: true, deploy: 'ask' },
    memory_policy: 'conversation',
    model_backend: 'deepseek',
  },
  {
    id: 'blank',
    name: '空白 Agent',
    description: '从一个最小、安全的 Agent 开始配置。',
    category: 'general',
    capabilities: ['助手'],
    builder_profile: DEFAULT_PROFILE,
    permissions: DEFAULT_PERMISSIONS,
    memory_policy: 'conversation',
    model_backend: 'deepseek',
  },
];

const PROVIDER_LABELS: Record<CreatableAgentProvider, string> = {
  builtin: 'AgentHub 内置',
  claude_code: 'Claude Code',
  codex: 'Codex',
  opencode: 'OpenCode',
};

const DEFAULT_MODEL_PROVIDERS: ModelProviderInfo[] = [
  {
    provider: 'deepseek',
    company_name: 'DeepSeek',
    protocol: 'openai_compatible',
    default_model: 'deepseek-v4-flash',
    models: ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner'],
    requires_base_url: false,
    default_base_url: 'https://api.deepseek.com',
  },
  {
    provider: 'openai',
    company_name: 'OpenAI',
    protocol: 'openai_compatible',
    default_model: 'gpt-5.4-mini',
    models: [
      'gpt-5.5',
      'gpt-5.4',
      'gpt-5.4-mini',
      'gpt-5.4-nano',
      'gpt-5.2',
      'gpt-5.2-pro',
      'gpt-5.1',
      'gpt-5',
      'gpt-5-mini',
      'gpt-5-nano',
      'o3-pro',
      'o3',
      'o4-mini',
      'gpt-4.1',
      'gpt-4.1-mini',
      'gpt-4.1-nano',
      'gpt-4o',
      'gpt-4o-mini',
    ],
    requires_base_url: false,
  },
  {
    provider: 'anthropic',
    company_name: 'Anthropic Claude',
    protocol: 'anthropic',
    default_model: 'claude-sonnet-4-6',
    models: [
      'claude-opus-4-8',
      'claude-opus-4-7',
      'claude-opus-4-6',
      'claude-sonnet-4-6',
      'claude-haiku-4-5',
      'claude-haiku-4-5-20251001',
    ],
    requires_base_url: false,
  },
  {
    provider: 'openai_compatible',
    company_name: 'OpenAI 兼容接口',
    protocol: 'openai_compatible',
    default_model: 'custom',
    models: ['custom'],
    requires_base_url: true,
  },
];

const POLICY_LABELS: Record<AgentBuilderProfile['clarification_policy'], string> = {
  ask_first: '先追问再行动',
  balanced: '平衡追问与默认判断',
  decide_with_defaults: '优先使用安全默认值',
};

const POLICY_DESCRIPTIONS: Record<AgentBuilderProfile['clarification_policy'], string> = {
  ask_first: '需求不清时先问一个关键问题，再开始行动。',
  balanced: '常规问题直接处理，关键取舍再追问。',
  decide_with_defaults: '尽量少打断用户，使用安全默认值推进。',
};

const TEMPLATE_OVERRIDES = new Map(FALLBACK_TEMPLATES.map((template) => [template.id, template]));

function localizeTemplate(template: AgentTemplate): AgentTemplate {
  return TEMPLATE_OVERRIDES.get(template.id) ?? template;
}

function listToText(value: string[]): string {
  return value.join('\n');
}

function textToList(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildSystemPrompt(profile: AgentBuilderProfile): string {
  return [
    `角色：${profile.role || '自定义 Agent'}`,
    `用途：${profile.purpose || '帮助用户处理一个明确任务。'}`,
    profile.tone ? `语气：${profile.tone}` : '',
    profile.output_style ? `输出方式：${profile.output_style}` : '',
    profile.goals.length ? `目标：\n${profile.goals.map((item) => `- ${item}`).join('\n')}` : '',
    profile.do_not_do.length
      ? `边界：\n${profile.do_not_do.map((item) => `- ${item}`).join('\n')}`
      : '',
    `澄清策略：${POLICY_LABELS[profile.clarification_policy]}`,
  ]
    .filter(Boolean)
    .join('\n\n');
}

function parseMcpServers(value: string): Array<Record<string, unknown>> | null {
  if (!value.trim()) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    if (Array.isArray(parsed) && parsed.every((item) => item && typeof item === 'object')) {
      return parsed as Array<Record<string, unknown>>;
    }
  } catch {
    return null;
  }
  return null;
}

function buildModelProfile(
  source: AgentModelProfile['source'],
  account: ModelAccount | undefined,
): AgentModelProfile {
  if (source === 'user_account' && account) {
    return {
      source: 'user_account',
      account_id: account.id,
      provider: account.provider,
      model: account.model,
    };
  }
  return {
    source: 'agenthub_default',
    provider: 'deepseek',
    model: 'deepseek-v4-flash',
  };
}

function modelSummary(
  source: AgentModelProfile['source'],
  account: ModelAccount | undefined,
  _fallbackModel: string,
): string {
  if (source === 'user_account' && account) {
    return `${account.display_name} · ${account.model}（已保存密钥）`;
  }
  return 'AgentHub 免费 DeepSeek（无需 API Key）';
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
  const templateQuery = useAgentTemplates();
  const providerQuery = useModelProviders();
  const modelAccounts = useModelAccounts();
  const templates = templateQuery.data?.items.length
    ? templateQuery.data.items.map(localizeTemplate)
    : FALLBACK_TEMPLATES;
  const [stepIndex, setStepIndex] = useState(0);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [capabilities, setCapabilities] = useState('');
  const [profile, setProfile] = useState<AgentBuilderProfile>(DEFAULT_PROFILE);
  const [goalsText, setGoalsText] = useState(listToText(DEFAULT_PROFILE.goals));
  const [boundariesText, setBoundariesText] = useState(listToText(DEFAULT_PROFILE.do_not_do));
  const [startersText, setStartersText] = useState(listToText(DEFAULT_PROFILE.starters));
  const [permissions, setPermissions] = useState<AgentPermissions>(DEFAULT_PERMISSIONS);
  const [memoryPolicy, setMemoryPolicy] = useState<AgentMemoryPolicy>('conversation');
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [provider, setProvider] = useState<CreatableAgentProvider>('builtin');
  const [model, setModel] = useState('deepseek');
  const [modelSource, setModelSource] = useState<AgentModelProfile['source']>('agenthub_default');
  const [selectedModelAccountId, setSelectedModelAccountId] = useState('');
  const [accountProvider, setAccountProvider] = useState<ModelProvider>('deepseek');
  const [accountDisplayName, setAccountDisplayName] = useState('');
  const [accountApiKey, setAccountApiKey] = useState('');
  const [accountModel, setAccountModel] = useState('deepseek-v4-flash');
  const [accountBaseUrl, setAccountBaseUrl] = useState('');
  const [accountError, setAccountError] = useState('');
  const [deletingModelAccountId, setDeletingModelAccountId] = useState('');
  const [maxIterations, setMaxIterations] = useState(10);
  const [mcpServersJson, setMcpServersJson] = useState('[]');
  const [mcpError, setMcpError] = useState('');

  const step = STEP_IDS[stepIndex] ?? 'basics';
  const selectedTemplate = templateId ? templates.find((template) => template.id === templateId) : null;
  const providerItems = providerQuery.data?.items ?? DEFAULT_MODEL_PROVIDERS;
  const accountItems = modelAccounts.accounts.data?.items ?? [];
  const selectedModelAccount = accountItems.find((account) => account.id === selectedModelAccountId);
  const normalizedProfile = useMemo(
    () => ({
      ...profile,
      purpose: description.trim() || profile.purpose,
      goals: textToList(goalsText),
      do_not_do: textToList(boundariesText),
      starters: textToList(startersText),
    }),
    [boundariesText, description, goalsText, profile, startersText],
  );
  const previewPrompt = buildSystemPrompt(normalizedProfile);

  if (!open) return null;

  function applyTemplate(template: AgentTemplate) {
    setTemplateId(template.id);
    setName(template.name);
    setDescription(template.description);
    setCapabilities(template.capabilities.join(', '));
    setProfile(template.builder_profile);
    setGoalsText(listToText(template.builder_profile.goals));
    setBoundariesText(listToText(template.builder_profile.do_not_do));
    setStartersText(listToText(template.builder_profile.starters));
    setPermissions(template.permissions);
    setMemoryPolicy(template.memory_policy);
    setModel(template.model_backend);
  }

  function clearTemplate() {
    setTemplateId(null);
    setName('');
    setDescription('');
    setCapabilities('');
    setProfile(DEFAULT_PROFILE);
    setGoalsText(listToText(DEFAULT_PROFILE.goals));
    setBoundariesText(listToText(DEFAULT_PROFILE.do_not_do));
    setStartersText(listToText(DEFAULT_PROFILE.starters));
    setPermissions(DEFAULT_PERMISSIONS);
    setMemoryPolicy('conversation');
    setModel('deepseek');
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedMcpServers = parseMcpServers(mcpServersJson);
    if (parsedMcpServers === null) {
      setMcpError('MCP 服务器配置必须是 JSON 数组。');
      return;
    }
    setMcpError('');
    const modelProfile = buildModelProfile(modelSource, selectedModelAccount);
    onCreate({
      name: name.trim(),
      provider,
      model,
      maxIterations,
      capabilities: textToList(capabilities),
      systemPrompt: previewPrompt,
      builderProfile: normalizedProfile,
      permissions,
      memoryPolicy,
      mcpServers: parsedMcpServers,
      modelProfile,
    });
  }

  async function createBackpackAccount() {
    const definition = providerItems.find((item) => item.provider === accountProvider);
    const nextModel = accountModel.trim() || definition?.default_model || 'custom';
    const nextName =
      accountDisplayName.trim() ||
      `${definition?.company_name ?? accountProvider} ${nextModel}`;
    if (!accountApiKey.trim()) {
      setAccountError('请输入 API Key。');
      return;
    }
    if (definition?.requires_base_url && !accountBaseUrl.trim()) {
      setAccountError('OpenAI 兼容接口需要填写 Base URL。');
      return;
    }
    setAccountError('');
    try {
      const created = await modelAccounts.create.mutateAsync({
        display_name: nextName,
        provider: accountProvider,
        api_key: accountApiKey.trim(),
        model: nextModel,
        base_url: accountBaseUrl.trim() || undefined,
      });
      setModelSource('user_account');
      setSelectedModelAccountId(created.id);
      setModel(nextModel);
      setAccountApiKey('');
      setAccountDisplayName('');
      await modelAccounts.verify.mutateAsync(created.id);
    } catch (error) {
      setAccountError(extractApiError(error));
    }
  }

  async function deleteBackpackAccount(accountId: string) {
    const account = accountItems.find((item) => item.id === accountId);
    const confirmed = window.confirm(
      `确定删除模型账号“${account?.display_name ?? '这个账号'}”吗？已经绑定到 Agent 的账号不能删除。`,
    );
    if (!confirmed) return;
    setAccountError('');
    setDeletingModelAccountId(accountId);
    try {
      await modelAccounts.remove.mutateAsync(accountId);
      if (selectedModelAccountId === accountId) {
        setSelectedModelAccountId('');
        setModelSource('agenthub_default');
        setModel('deepseek');
      }
    } catch (error) {
      setAccountError(extractApiError(error));
    } finally {
      setDeletingModelAccountId('');
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 sm:px-4 sm:py-6 backdrop-blur-sm">
      <form
        onSubmit={submit}
        className="flex h-[100dvh] w-full max-w-5xl flex-col overflow-hidden border border-slate-700 bg-slate-900 shadow-2xl shadow-black/40 sm:max-h-[calc(100dvh-3rem)] sm:rounded-md"
      >
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-light">
              <Sparkles className="h-3.5 w-3.5" />
              自定义 Agent 构建器
            </div>
            <h2 className="mt-1 text-base font-semibold text-white">创建自定义 Agent</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-800 hover:text-white"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden md:grid md:grid-cols-[13rem_minmax(0,1fr)_18rem]">
          <nav className="border-b border-slate-800 p-4 md:border-b-0 md:border-r">
            <div className="grid grid-cols-4 gap-2 md:block md:space-y-2">
              {STEP_IDS.map((item, index) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setStepIndex(index)}
                  className={cn(
                    'flex items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-medium md:w-full md:justify-start',
                    index === stepIndex
                      ? 'bg-brand text-white'
                      : 'bg-slate-950 text-slate-400 hover:bg-slate-800 hover:text-white',
                  )}
                >
                  <span>{index + 1}</span>
                  <span className="hidden md:inline">{STEP_LABELS[item]}</span>
                </button>
              ))}
            </div>
          </nav>

          <div className="min-h-0 overflow-y-auto p-5 scrollbar-thin">
            {step === 'basics' && (
              <div className="space-y-5">
                <Field label="名称" value={name} onChange={setName} />
                <Field label="一句话用途" value={description} onChange={setDescription} />
                <Field label="能力标签" value={capabilities} onChange={setCapabilities} />
                <div>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h3 className="text-sm font-semibold text-white">快捷模板（可选）</h3>
                    {templateId && (
                      <button
                        type="button"
                        onClick={clearTemplate}
                        className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white"
                      >
                        不使用模板
                      </button>
                    )}
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {templates.map((template) => (
                      <button
                        key={template.id}
                        type="button"
                        onClick={() => applyTemplate(template)}
                        className={cn(
                          'rounded-md border p-4 text-left transition',
                          template.id === selectedTemplate?.id
                            ? 'border-brand bg-brand/10'
                            : 'border-slate-800 bg-slate-950 hover:border-slate-700',
                        )}
                      >
                        <div className="text-sm font-medium text-white">{template.name}</div>
                        <div className="mt-1 text-xs leading-5 text-slate-500">
                          {template.description}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {step === 'behavior' && (
              <div className="space-y-5">
                <Field
                  label="角色"
                  value={profile.role ?? ''}
                  onChange={(value) => setProfile((current) => ({ ...current, role: value }))}
                />
                <Field
                  label="用途"
                  value={profile.purpose ?? ''}
                  onChange={(value) => setProfile((current) => ({ ...current, purpose: value }))}
                />
                <TextArea label="目标" value={goalsText} onChange={setGoalsText} rows={4} />
                <Field
                  label="语气"
                  value={profile.tone ?? ''}
                  onChange={(value) => setProfile((current) => ({ ...current, tone: value }))}
                />
                <TextArea
                  label="边界"
                  value={boundariesText}
                  onChange={setBoundariesText}
                  rows={4}
                />
                <div>
                  <span className="text-xs font-medium text-slate-400">澄清策略</span>
                  <div className="mt-2 grid gap-2 md:grid-cols-3">
                    {Object.entries(POLICY_LABELS).map(([policy, label]) => {
                      const value = policy as AgentBuilderProfile['clarification_policy'];
                      const selected = profile.clarification_policy === value;
                      return (
                        <button
                          key={value}
                          type="button"
                          onClick={() =>
                            setProfile((current) => ({
                              ...current,
                              clarification_policy: value,
                            }))
                          }
                          className={cn(
                            'rounded-md border p-3 text-left transition',
                            selected
                              ? 'border-brand/80 bg-brand/10 text-white'
                              : 'border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700',
                          )}
                        >
                          <div className="text-sm font-medium">{label}</div>
                          <div className="mt-1 text-xs leading-5 text-slate-500">
                            {POLICY_DESCRIPTIONS[value]}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
                <TextArea
                  label="开场提示词"
                  value={startersText}
                  onChange={setStartersText}
                  rows={3}
                />
              </div>
            )}

            {step === 'permissions' && (
              <div className="space-y-4">
                <PermissionToggle
                  title="读取 Workspace 文件"
                  checked={permissions.workspace_read}
                  onChange={(checked) =>
                    setPermissions((current) => ({
                      ...current,
                      workspace_read: checked,
                      workspace_write: checked ? current.workspace_write : false,
                    }))
                  }
                />
                <PermissionToggle
                  title="修改 Workspace 文件"
                  checked={permissions.workspace_write}
                  onChange={(checked) =>
                    setPermissions((current) => ({
                      ...current,
                      workspace_read: checked || current.workspace_read,
                      workspace_write: checked,
                    }))
                  }
                />
                <PermissionToggle
                  title="运行命令"
                  checked={permissions.run_commands !== 'never'}
                  onChange={(checked) =>
                    setPermissions((current) => ({
                      ...current,
                      run_commands: checked ? 'ask' : 'never',
                    }))
                  }
                />
                <PermissionToggle
                  title="使用网络或外部 API"
                  checked={permissions.network !== 'never'}
                  onChange={(checked) =>
                    setPermissions((current) => ({
                      ...current,
                      network: checked ? 'ask' : 'never',
                    }))
                  }
                />
                <label className="block">
                  <span className="text-xs font-medium text-slate-400">记忆</span>
                  <select
                    value={memoryPolicy}
                    onChange={(event) => setMemoryPolicy(event.target.value as AgentMemoryPolicy)}
                    className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
                  >
                    <option value="none">不记忆</option>
                    <option value="conversation">仅当前会话</option>
                    <option value="project" disabled>
                      项目记忆（后续支持）
                    </option>
                    <option value="user" disabled>
                      用户记忆（后续支持）
                    </option>
                  </select>
                </label>
              </div>
            )}

            {step === 'publish' && (
              <div className="space-y-5">
                <ModelBackpackSection
                  providers={providerItems}
                  accounts={accountItems}
                  modelSource={modelSource}
                  selectedAccountId={selectedModelAccountId}
                  accountProvider={accountProvider}
                  accountDisplayName={accountDisplayName}
                  accountApiKey={accountApiKey}
                  accountModel={accountModel}
                  accountBaseUrl={accountBaseUrl}
                  error={accountError}
                  isSaving={modelAccounts.create.isPending || modelAccounts.verify.isPending}
                  deletingAccountId={deletingModelAccountId}
                  onModelSourceChange={setModelSource}
                  onSelectedAccountChange={(accountId) => {
                    const account = accountItems.find((item) => item.id === accountId);
                    setSelectedModelAccountId(accountId);
                    if (account) setModel(account.model);
                  }}
                  onAccountProviderChange={(nextProvider) => {
                    const definition = providerItems.find((item) => item.provider === nextProvider);
                    setAccountProvider(nextProvider);
                    setAccountModel(definition?.default_model ?? 'custom');
                    setAccountBaseUrl(definition?.default_base_url ?? '');
                  }}
                  onAccountDisplayNameChange={setAccountDisplayName}
                  onAccountApiKeyChange={setAccountApiKey}
                  onAccountModelChange={(nextModel) => {
                    setAccountModel(nextModel);
                    setModel(nextModel);
                  }}
                  onAccountBaseUrlChange={setAccountBaseUrl}
                  onCreateAccount={() => void createBackpackAccount()}
                  onDeleteAccount={(accountId) => void deleteBackpackAccount(accountId)}
                />
                <div className="rounded-md border border-slate-800 bg-slate-950 p-4">
                  <div className="flex items-center gap-2 text-sm font-medium text-white">
                    <ShieldCheck className="h-4 w-4 text-emerald-400" />
                    创建前检查
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    下面是这个 Agent 创建后的实际使用方式，确认无误后即可创建。
                  </p>
                  <dl className="mt-4 space-y-3 text-sm">
                    <SummaryRow
                      label="模型"
                      value={modelSummary(
                        modelSource,
                        selectedModelAccount,
                        model,
                      )}
                    />
                    <SummaryRow label="能做什么" value={toolSummary(permissions)} />
                    <SummaryRow label="记忆范围" value={formatMemoryPolicy(memoryPolicy)} />
                  </dl>
                </div>

                <button
                  type="button"
                  onClick={() => setAdvancedOpen((value) => !value)}
                  className="hidden"
                >
                  <SlidersHorizontal className="h-4 w-4" />
                  高级配置
                </button>
                {advancedOpen && (
                  <div className="space-y-4 rounded-md border border-slate-800 bg-slate-950 p-4">
                    <label className="block">
                      <span className="text-xs font-medium text-slate-400">运行时</span>
                      <select
                        value={provider}
                        onChange={(event) => setProvider(event.target.value as CreatableAgentProvider)}
                        className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
                      >
                        {Object.entries(PROVIDER_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <Field label="模型后端" value={model} onChange={setModel} />
                    <label className="block">
                      <span className="text-xs font-medium text-slate-400">最大迭代次数</span>
                      <input
                        type="number"
                        min={1}
                        max={50}
                        value={maxIterations}
                        onChange={(event) => setMaxIterations(Number(event.target.value))}
                        className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
                      />
                    </label>
                    <TextArea
                      label="MCP 服务器 JSON"
                      value={mcpServersJson}
                      onChange={setMcpServersJson}
                      rows={5}
                      monospace
                    />
                    {mcpError && <div className="text-xs text-rose-300">{mcpError}</div>}
                  </div>
                )}
              </div>
            )}
          </div>

          <aside className="hidden min-h-0 border-l border-slate-800 p-4 md:block">
            <div className="rounded-md border border-slate-800 bg-slate-950 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-white">
                <Bot className="h-4 w-4 text-brand-light" />
                预览
              </div>
              <div className="mt-4 text-sm font-semibold text-white">{name || '新 Agent'}</div>
              <div className="mt-1 text-xs leading-5 text-slate-500">{description}</div>
              <div className="mt-4 flex flex-wrap gap-2">
                {textToList(capabilities).map((capability) => (
                  <span key={capability} className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300">
                    {capability}
                  </span>
                ))}
              </div>
              <pre className="mt-4 max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-slate-800 bg-slate-900 p-3 text-xs leading-5 text-slate-400">
                {previewPrompt}
              </pre>
            </div>
          </aside>
        </div>

        <div className="flex shrink-0 items-center justify-between gap-3 border-t border-slate-800 px-5 pb-[max(env(safe-area-inset-bottom),1rem)] pt-4">
          <button
            type="button"
            onClick={() => setStepIndex((index) => Math.max(0, index - 1))}
            disabled={stepIndex === 0}
            className="inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
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
              disabled={!name.trim()}
              className="inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
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

function ModelBackpackSection({
  providers,
  accounts,
  modelSource,
  selectedAccountId,
  accountProvider,
  accountDisplayName,
  accountApiKey,
  accountModel,
  accountBaseUrl,
  error,
  isSaving,
  deletingAccountId,
  onModelSourceChange,
  onSelectedAccountChange,
  onAccountProviderChange,
  onAccountDisplayNameChange,
  onAccountApiKeyChange,
  onAccountModelChange,
  onAccountBaseUrlChange,
  onCreateAccount,
  onDeleteAccount,
}: {
  providers: ModelProviderInfo[];
  accounts: ModelAccount[];
  modelSource: AgentModelProfile['source'];
  selectedAccountId: string;
  accountProvider: ModelProvider;
  accountDisplayName: string;
  accountApiKey: string;
  accountModel: string;
  accountBaseUrl: string;
  error: string;
  isSaving: boolean;
  deletingAccountId: string;
  onModelSourceChange: (value: AgentModelProfile['source']) => void;
  onSelectedAccountChange: (value: string) => void;
  onAccountProviderChange: (value: ModelProvider) => void;
  onAccountDisplayNameChange: (value: string) => void;
  onAccountApiKeyChange: (value: string) => void;
  onAccountModelChange: (value: string) => void;
  onAccountBaseUrlChange: (value: string) => void;
  onCreateAccount: () => void;
  onDeleteAccount: (accountId: string) => void;
}) {
  const selectedProvider = providers.find((item) => item.provider === accountProvider) ?? providers[0];
  const modelOptions = selectedProvider?.models ?? ['custom'];
  const providerNameById = new Map(providers.map((item) => [item.provider, item.company_name]));
  return (
    <section className="rounded-md border border-slate-800 bg-slate-950 p-4">
      <div className="text-sm font-medium text-white">大模型设置</div>
      <p className="mt-1 text-xs leading-5 text-slate-500">
        默认使用 AgentHub 免费 DeepSeek。也可以把自己的 API Key 保存到模型背包，再绑定给这个 Agent。
      </p>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <button
          type="button"
          onClick={() => onModelSourceChange('agenthub_default')}
          className={cn(
            'rounded-md border p-3 text-left text-sm transition',
            modelSource === 'agenthub_default'
              ? 'border-brand bg-brand/10 text-white'
              : 'border-slate-800 text-slate-300 hover:border-slate-700',
          )}
        >
          <div className="font-medium">AgentHub 免费 DeepSeek</div>
          <div className="mt-1 text-xs text-slate-500">无需填写 API Key，适合作为默认配置。</div>
        </button>
        <button
          type="button"
          onClick={() => onModelSourceChange('user_account')}
          className={cn(
            'rounded-md border p-3 text-left text-sm transition',
            modelSource === 'user_account'
              ? 'border-brand bg-brand/10 text-white'
              : 'border-slate-800 text-slate-300 hover:border-slate-700',
          )}
        >
          <div className="font-medium">使用我的 API</div>
          <div className="mt-1 text-xs text-slate-500">选择公司、保存密钥、指定模型。</div>
        </button>
      </div>

      {modelSource === 'user_account' && (
        <div className="mt-4 space-y-4 rounded-md border border-slate-800 bg-slate-900/60 p-3">
          {accounts.length ? (
            <div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-medium text-slate-400">已保存账号</span>
                <span className="text-[11px] text-slate-500">点击账号即可绑定给当前 Agent</span>
              </div>
              <div className="mt-2 grid gap-2">
                {accounts.map((account) => {
                  const selected = selectedAccountId === account.id;
                  const deleting = deletingAccountId === account.id;
                  return (
                    <div
                      key={account.id}
                      className={cn(
                        'flex items-center gap-3 rounded-md border bg-slate-950 px-3 py-3 text-left transition',
                        selected
                          ? 'border-brand/80 shadow-sm shadow-brand/10'
                          : 'border-slate-800 hover:border-slate-700',
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => onSelectedAccountChange(account.id)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="truncate text-sm font-medium text-slate-100">
                            {account.display_name}
                          </span>
                          {selected && (
                            <span className="rounded-full bg-brand/15 px-2 py-0.5 text-[11px] font-medium text-brand-light">
                              当前使用
                            </span>
                          )}
                          <span
                            className={cn(
                              'rounded-full px-2 py-0.5 text-[11px]',
                              account.status === 'ready'
                                ? 'bg-emerald-500/10 text-emerald-300'
                                : account.status === 'unavailable'
                                  ? 'bg-rose-500/10 text-rose-300'
                                  : 'bg-slate-800 text-slate-400',
                            )}
                          >
                            {formatModelAccountStatus(account.status)}
                          </span>
                        </div>
                        <div className="mt-1 truncate text-xs text-slate-500">
                          {providerNameById.get(account.provider) ?? account.provider} · {account.model} ·{' '}
                          {account.api_key_preview}
                        </div>
                      </button>
                      <button
                        type="button"
                        disabled={deleting}
                        onClick={() => onDeleteAccount(account.id)}
                        className="rounded-md border border-slate-800 p-2 text-slate-400 transition hover:border-rose-500/50 hover:bg-rose-500/10 hover:text-rose-300 disabled:cursor-not-allowed disabled:opacity-50"
                        title="删除模型账号"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-slate-700 px-3 py-2 text-xs text-slate-500">
              还没有保存过模型账号，可以在下面新增一个。
            </div>
          )}

          <div className="space-y-3">
            <div>
              <span className="text-xs font-medium text-slate-400">模型公司</span>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {providers.map((item) => {
                  const selected = item.provider === accountProvider;
                  return (
                    <button
                      key={item.provider}
                      type="button"
                      onClick={() => onAccountProviderChange(item.provider)}
                      className={cn(
                        'rounded-md border px-3 py-2 text-left text-sm transition',
                        selected
                          ? 'border-brand/80 bg-brand/10 text-white'
                          : 'border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700',
                      )}
                    >
                      {item.company_name}
                    </button>
                  );
                })}
              </div>
            </div>
            <div>
              <span className="text-xs font-medium text-slate-400">调用模型</span>
              <div className="mt-2 max-h-36 overflow-y-auto rounded-md border border-slate-800 bg-slate-950 p-2">
                <div className="flex flex-wrap gap-2">
                  {modelOptions.map((item) => {
                    const selected = item === accountModel;
                    return (
                      <button
                        key={item}
                        type="button"
                        onClick={() => onAccountModelChange(item)}
                        className={cn(
                          'rounded-md border px-2.5 py-1.5 text-xs transition',
                          selected
                            ? 'border-brand/80 bg-brand/10 text-brand-light'
                            : 'border-slate-800 bg-slate-900 text-slate-400 hover:border-slate-700 hover:text-slate-200',
                        )}
                      >
                        {item}
                      </button>
                    );
                  })}
                </div>
              </div>
              <label className="mt-2 block">
                <span className="sr-only">手动输入模型名</span>
                <input
                  value={accountModel}
                  onChange={(event) => onAccountModelChange(event.target.value)}
                  placeholder="也可以手动输入模型名"
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-brand"
                />
              </label>
            </div>
          </div>

          {selectedProvider?.requires_base_url && (
            <Field label="Base URL" value={accountBaseUrl} onChange={onAccountBaseUrlChange} />
          )}
          <Field label="账号名称（可选）" value={accountDisplayName} onChange={onAccountDisplayNameChange} />
          <label className="block">
            <span className="text-xs font-medium text-slate-400">API Key</span>
            <input
              type="password"
              value={accountApiKey}
              onChange={(event) => onAccountApiKeyChange(event.target.value)}
              className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
            />
          </label>
          {error && (
            <div className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
              {error}
            </div>
          )}
          <button
            type="button"
            disabled={isSaving}
            onClick={onCreateAccount}
            className="rounded-md bg-brand px-3 py-2 text-sm font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSaving ? '正在保存并验证...' : '保存到模型背包'}
          </button>
        </div>
      )}
    </section>
  );
}

function formatModelAccountStatus(status: ModelAccount['status']) {
  if (status === 'ready') return '可用';
  if (status === 'unavailable') return '不可用';
  return '未验证';
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
      <span className="text-xs font-medium text-slate-400">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-brand"
      />
    </label>
  );
}

function TextArea({
  label,
  value,
  onChange,
  rows,
  monospace = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows: number;
  monospace?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-400">{label}</span>
      <textarea
        value={value}
        rows={rows}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          'mt-2 w-full resize-none rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm leading-6 text-slate-100 outline-none focus:border-brand',
          monospace && 'font-mono text-xs',
        )}
      />
    </label>
  );
}

function PermissionToggle({
  title,
  checked,
  onChange,
}: {
  title: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-4 rounded-md border border-slate-800 bg-slate-950 p-4">
      <span className="text-sm font-medium text-slate-200">{title}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 accent-brand"
      />
    </label>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-1 text-slate-200">{value}</dd>
    </div>
  );
}

function toolSummary(permissions: AgentPermissions): string {
  const tools = [];
  if (permissions.workspace_read || permissions.workspace_write) tools.push('查看 Workspace 文件');
  if (permissions.workspace_write) tools.push('修改 Workspace 文件');
  if (permissions.run_commands !== 'never') tools.push('需要确认后运行命令');
  if (permissions.network !== 'never') tools.push('需要确认后联网');
  return tools.length ? tools.join('、') : '只聊天，不读取文件、不运行命令';
}

function formatMemoryPolicy(policy: AgentMemoryPolicy): string {
  if (policy === 'none') return '不保存额外记忆';
  if (policy === 'conversation') return '只使用当前会话里的上下文';
  if (policy === 'project') return '项目范围记忆';
  return '用户长期记忆';
}
