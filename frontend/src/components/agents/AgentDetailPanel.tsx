import {
  Bot,
  CheckCircle2,
  Edit3,
  FileText,
  Layers3,
  Loader2,
  PlayCircle,
  ShieldCheck,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { AgentAvatar } from './AgentAvatar';
import { useAgentAssets } from '@/hooks/useAgentAssets';
import { useAgentTestRun } from '@/hooks/useAgentRuntimeChecks';
import { extractApiError } from '@/lib/api';
import type { Agent, AgentSkillRef, ContentBlock } from '@/lib/types';
import { cn } from '@/lib/utils';

const BASE_AGENT_LABELS: Record<string, string> = {
  'claude-code': 'Claude Code',
  'codex-helper': 'Codex Helper',
  'opencode-helper': 'OpenCode Helper',
};

interface WrapperProfile {
  role?: string | null;
  purpose?: string | null;
  planning_profile?: string | null;
  planning_strengths?: string[];
  planning_weaknesses?: string[];
  preferred_task_types?: string[];
  capabilities?: string[];
  output_style?: string | null;
  boundaries?: string[];
}

type EditingSkill = { item: AgentSkillRef; name: string; description: string };

export function AgentDetailPanel({
  agent,
  onEdit,
  onDelete,
  isDeleting = false,
  presentation = 'desktop',
  onClose,
}: {
  agent: Agent | null;
  onEdit?: (agent: Agent) => void;
  onDelete?: (agent: Agent) => void;
  isDeleting?: boolean;
  presentation?: 'desktop' | 'mobile';
  onClose?: () => void;
}) {
  const skillInputRef = useRef<HTMLInputElement | null>(null);
  const [skillName, setSkillName] = useState('');
  const [skillDescription, setSkillDescription] = useState('');
  const [assetError, setAssetError] = useState('');
  const [editingSkill, setEditingSkill] = useState<EditingSkill | null>(null);
  const [testPrompt, setTestPrompt] = useState('请介绍一下你适合处理什么任务。');

  const agentAssets = useAgentAssets(agent?.id);
  const testRun = useAgentTestRun();
  const panelClassName = cn(
    'h-full shrink-0 overflow-y-auto bg-white p-5 scrollbar-thin dark:bg-slate-900',
    presentation === 'desktop'
      ? 'hidden w-80 border-l border-slate-200 dark:border-slate-800 xl:block'
      : 'block w-full',
  );

  useEffect(() => {
    setSkillName('');
    setSkillDescription('');
    setAssetError('');
    setEditingSkill(null);
    setTestPrompt('请介绍一下你适合处理什么任务。');
  }, [agent?.id]);

  if (!agent) {
    return (
      <aside className={panelClassName}>
        <div className="flex h-full items-center justify-center rounded-md border border-dashed border-slate-300 text-sm text-slate-600 dark:border-slate-800 dark:text-slate-500">
          选择一个 Agent 查看详情
        </div>
      </aside>
    );
  }

  const currentAgent = agent;
  const canManage = !currentAgent.is_builtin;
  const skills = readConfigItems<AgentSkillRef>(currentAgent.config, 'skills');
  const profile = readWrapperProfile(currentAgent.config);
  const baseLabel = baseAgentSummary(currentAgent.config, currentAgent.provider);
  const assets = agentAssets.assets.data;
  const history = agentAssets.history.data;
  const usage = agentAssets.usage.data;

  async function handleSkillFile(file: File | undefined) {
    if (!file) return;
    setAssetError('');
    try {
      await agentAssets.uploadSkill.mutateAsync({
        agentId: currentAgent.id,
        file,
        name: skillName.trim() || undefined,
        description: skillDescription.trim() || undefined,
      });
      setSkillName('');
      setSkillDescription('');
    } catch (error) {
      setAssetError(extractApiError(error));
    } finally {
      if (skillInputRef.current) skillInputRef.current.value = '';
    }
  }

  async function deleteSkill(skillId: string) {
    if (!window.confirm('仅从这个 Agent 解绑该 Skill，原始上传文件会保留。继续？')) {
      return;
    }
    setAssetError('');
    try {
      await agentAssets.deleteSkill.mutateAsync({ agentId: currentAgent.id, skillId });
    } catch (error) {
      setAssetError(extractApiError(error));
    }
  }

  async function submitSkillEdit() {
    if (!editingSkill) return;
    setAssetError('');
    try {
      await agentAssets.updateSkill.mutateAsync({
        agentId: currentAgent.id,
        skillId: editingSkill.item.skill_id,
        name: editingSkill.name.trim() || undefined,
        description: editingSkill.description.trim() || undefined,
      });
      setEditingSkill(null);
    } catch (error) {
      setAssetError(extractApiError(error));
    }
  }

  async function runAgentTest() {
    if (!testPrompt.trim()) return;
    try {
      await testRun.mutateAsync({ agentId: currentAgent.id, prompt: testPrompt.trim() });
    } catch {
      // Mutation state renders the failure; keep the panel open.
    }
  }

  return (
    <aside className={panelClassName}>
      {presentation === 'mobile' && (
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-slate-950 dark:text-white">Agent 详情</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
            aria-label="关闭 Agent 详情"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <section className="rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="flex items-center gap-3">
          <AgentAvatar agent={agent} size="lg" />
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-slate-950 dark:text-white">
              {agent.name}
            </h2>
            <p className="mt-1 text-xs uppercase tracking-wide text-slate-600 dark:text-slate-500">
              {agent.provider}
            </p>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          {agent.is_builtin ? (
            <>
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              内置 Agent
            </>
          ) : (
            <>
              <Bot className="h-4 w-4 text-brand dark:text-brand-light" />
              服务器 Agent 套壳
            </>
          )}
        </div>

        {!agent.is_builtin ? (
          <div className="mt-4 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => onEdit?.(agent)}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
            >
              <Edit3 className="h-4 w-4" />
              编辑
            </button>
            <button
              type="button"
              onClick={() => onDelete?.(agent)}
              disabled={isDeleting}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-rose-300 px-3 py-2 text-sm text-rose-600 transition hover:bg-rose-50 disabled:opacity-50 dark:border-rose-500/40 dark:text-rose-300 dark:hover:bg-rose-500/10"
            >
              {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              删除
            </button>
          </div>
        ) : null}
      </section>

      <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
          <FileText className="h-4 w-4 text-brand dark:text-brand-light" />
          套壳配置
        </div>
        <dl className="mt-4 space-y-3 text-sm">
          <InfoRow label="套壳自" value={baseLabel} />
          <InfoRow label="用途" value={profile.purpose || '未填写'} />
          <InfoRow label="角色" value={profile.role || '未填写'} />
          <InfoRow label="调度描述" value={profile.planning_profile || '未填写'} />
          <InfoRow label="输出风格" value={profile.output_style || '未填写'} />
        </dl>
        <ChipGroup title="擅长" items={profile.planning_strengths} />
        <ChipGroup title="不擅长" items={profile.planning_weaknesses} />
        <ChipGroup title="适合任务类型" items={profile.preferred_task_types} />
        <ChipGroup title="边界" items={profile.boundaries} />
      </section>

      <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
            <UploadCloud className="h-4 w-4 text-brand dark:text-brand-light" />
            Skills
          </div>
          {agentAssets.isPending ? <Loader2 className="h-4 w-4 animate-spin text-slate-500" /> : null}
        </div>

        <p className="mt-2 text-xs leading-5 text-slate-600 dark:text-slate-500">
          Skills 会作为额外能力说明注入到底座 Agent。当前版本只支持 Markdown / SKILL.md。
        </p>

        {assetError ? (
          <div className="mt-3 rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
            {assetError}
          </div>
        ) : null}

        {canManage ? (
          <div className="mt-4 space-y-2">
            <input
              ref={skillInputRef}
              type="file"
              accept=".md,.markdown,text/markdown"
              className="hidden"
              onChange={(event) => void handleSkillFile(event.currentTarget.files?.[0])}
            />
            <input
              value={skillName}
              onChange={(event) => setSkillName(event.target.value)}
              placeholder="Skill 名称（可选，默认读取 frontmatter）"
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
            <input
              value={skillDescription}
              onChange={(event) => setSkillDescription(event.target.value)}
              placeholder="Skill 描述（可选）"
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
            <button
              type="button"
              onClick={() => skillInputRef.current?.click()}
              className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <UploadCloud className="h-4 w-4" />
              上传 Skill
            </button>
          </div>
        ) : null}

        <div className="mt-4 space-y-2">
          {skills.length ? (
            skills.map((skill) => (
              <SkillRow
                key={skill.skill_id}
                skill={skill}
                canManage={canManage}
                onEdit={() =>
                  setEditingSkill({
                    item: skill,
                    name: skill.name,
                    description: skill.description,
                  })
                }
                onDelete={() => void deleteSkill(skill.skill_id)}
              />
            ))
          ) : (
            <div className="rounded-md border border-dashed border-slate-300 px-3 py-4 text-center text-xs text-slate-600 dark:border-slate-800 dark:text-slate-500">
              暂未绑定 Skill
            </div>
          )}
        </div>
      </section>

      <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
          <PlayCircle className="h-4 w-4 text-brand dark:text-brand-light" />
          测试运行
        </div>
        <textarea
          value={testPrompt}
          rows={3}
          onChange={(event) => setTestPrompt(event.target.value)}
          className="mt-3 w-full resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-6 text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
        />
        <button
          type="button"
          onClick={() => void runAgentTest()}
          disabled={testRun.isPending || !testPrompt.trim()}
          className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-md bg-brand px-3 py-2 text-sm font-medium text-white hover:bg-brand-hover disabled:opacity-50"
        >
          {testRun.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
          运行测试
        </button>
        {testRun.error ? (
          <div className="mt-3 rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
            {extractApiError(testRun.error)}
          </div>
        ) : null}
        {testRun.data ? (
          <div className="mt-3 rounded-md border border-slate-300 bg-white p-3 text-xs leading-5 text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
            <div className="mb-2 flex items-center gap-2 text-emerald-600 dark:text-emerald-300">
              <CheckCircle2 className="h-4 w-4" />
              {testRun.data.status === 'done' ? '测试完成' : '测试失败'}
            </div>
            {renderBlocks(testRun.data.content)}
          </div>
        ) : null}
      </section>

      <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
            <Layers3 className="h-4 w-4 text-brand dark:text-brand-light" />
            资产状态
          </div>
          {agentAssets.history.isLoading || agentAssets.usage.isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin text-slate-500" />
          ) : null}
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <Metric label="绑定" value={assets?.bindings.length ?? 0} />
          <Metric label="版本" value={history?.total ?? 0} />
          <Metric label="注入" value={usage?.total ?? 0} />
        </div>
        {agentAssets.history.isError || agentAssets.usage.isError ? (
          <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
            资产历史暂时不可用，不影响当前 Agent 使用。
          </div>
        ) : null}
      </section>

      {agent.system_prompt ? (
        <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
          <div className="text-sm font-medium text-slate-950 dark:text-white">系统提示词</div>
          <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap rounded-md border border-slate-300 bg-white p-3 text-xs leading-5 text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
            {agent.system_prompt}
          </pre>
        </section>
      ) : null}

      {editingSkill ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4">
          <div className="w-full max-w-sm rounded-md border border-slate-300 bg-white p-4 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <div className="text-sm font-semibold text-slate-950 dark:text-white">编辑 Skill</div>
            <input
              value={editingSkill.name}
              onChange={(event) =>
                setEditingSkill((current) =>
                  current ? { ...current, name: event.target.value } : current,
                )
              }
              className="mt-4 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <textarea
              value={editingSkill.description}
              rows={3}
              onChange={(event) =>
                setEditingSkill((current) =>
                  current ? { ...current, description: event.target.value } : current,
                )
              }
              className="mt-3 w-full resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditingSkill(null)}
                className="rounded-md px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void submitSkillEdit()}
                className="rounded-md bg-brand px-3 py-2 text-sm font-medium text-white hover:bg-brand-hover"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </aside>
  );
}

function readWrapperProfile(config: Agent['config']): WrapperProfile {
  if (!config || typeof config !== 'object') return {};
  const profile = (config as Record<string, unknown>).wrapper_profile;
  return profile && typeof profile === 'object' ? (profile as WrapperProfile) : {};
}

function readConfigItems<T>(config: Agent['config'], key: string): T[] {
  if (!config || typeof config !== 'object') return [];
  const value = (config as Record<string, unknown>)[key];
  return Array.isArray(value) ? (value as T[]) : [];
}

function baseAgentSummary(config: Agent['config'], provider: string): string {
  if (!config || typeof config !== 'object') return provider;
  const baseAgentId = (config as Record<string, unknown>).base_agent_id;
  return typeof baseAgentId === 'string' ? (BASE_AGENT_LABELS[baseAgentId] ?? baseAgentId) : provider;
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-600 dark:text-slate-500">{label}</dt>
      <dd className="mt-1 whitespace-pre-wrap text-slate-800 dark:text-slate-200">{value}</dd>
    </div>
  );
}

function ChipGroup({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="mt-4">
      <div className="text-xs text-slate-600 dark:text-slate-500">{title}</div>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.map((item) => (
          <span
            key={item}
            className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-300"
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function SkillRow({
  skill,
  canManage,
  onEdit,
  onDelete,
}: {
  skill: AgentSkillRef;
  canManage: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-md border border-slate-300 bg-white p-3 text-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="font-medium text-slate-950 dark:text-white">{skill.name}</div>
      <div className="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-500">
        {skill.description}
      </div>
      <div className="mt-2 text-xs text-slate-500">{skill.filename}</div>
      {canManage ? (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={onEdit}
            className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            编辑
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded-md border border-rose-300 px-2 py-1 text-xs text-rose-600 hover:bg-rose-50 dark:border-rose-500/40 dark:text-rose-300 dark:hover:bg-rose-500/10"
          >
            解绑
          </button>
        </div>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-300 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
      <div className="text-base font-semibold text-slate-950 dark:text-white">{value}</div>
      <div className="mt-1 text-slate-500">{label}</div>
    </div>
  );
}

function renderBlocks(blocks: ContentBlock[] | undefined) {
  if (!blocks?.length) {
    return <div className="text-slate-500">没有可见输出。</div>;
  }
  return blocks.map((block, index) => {
    if (block.type === 'text') {
      return (
        <p key={index} className="whitespace-pre-wrap">
          {block.text}
        </p>
      );
    }
    return (
      <div key={index} className="text-slate-500">
        {block.type}
      </div>
    );
  });
}
