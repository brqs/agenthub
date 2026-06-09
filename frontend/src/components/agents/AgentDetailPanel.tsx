import {
  Bot,
  Brain,
  CheckCircle2,
  Code2,
  Download,
  Edit3,
  FileText,
  History,
  Layers3,
  Loader2,
  MessageSquarePlus,
  PlayCircle,
  ShieldCheck,
  SquarePen,
  Trash2,
  UploadCloud,
  Wrench,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { AgentAvatar } from './AgentAvatar';
import { useAgentAssets } from '@/hooks/useAgentAssets';
import { useAgentMcpHealthCheck, useAgentTestRun } from '@/hooks/useAgentRuntimeChecks';
import { extractApiError } from '@/lib/api';
import { uploadDownloadUrl } from '@/lib/adapters/uploads';
import type {
  Agent,
  AgentAssetUsageEventRef,
  AgentAssetVersionRef,
  AgentBuilderProfile,
  AgentKnowledgeRef,
  AgentKnowledgeUsage,
  AgentModelProfile,
  AgentPermissions,
  AgentSkillRef,
  ContentBlock,
} from '@/lib/types';
import { cn } from '@/lib/utils';

const KNOWLEDGE_USAGE_OPTIONS: Array<{ value: AgentKnowledgeUsage; label: string }> = [
  { value: 'reference', label: '参考资料' },
  { value: 'policy', label: '规则/约束' },
  { value: 'template', label: '输出模板' },
  { value: 'example', label: '示例' },
];

type EditingAsset =
  | { kind: 'knowledge'; item: AgentKnowledgeRef }
  | { kind: 'skill'; item: AgentSkillRef };

interface AssetEditInput {
  label?: string;
  usage?: AgentKnowledgeUsage;
  name?: string;
  description?: string;
}

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
  const knowledgeInputRef = useRef<HTMLInputElement | null>(null);
  const skillInputRef = useRef<HTMLInputElement | null>(null);
  const [assetError, setAssetError] = useState('');
  const [knowledgeUsage, setKnowledgeUsage] = useState<AgentKnowledgeUsage>('reference');
  const [skillName, setSkillName] = useState('');
  const [skillDescription, setSkillDescription] = useState('');
  const [editingAsset, setEditingAsset] = useState<EditingAsset | null>(null);
  const [assetEditError, setAssetEditError] = useState('');
  const [testPrompt, setTestPrompt] = useState('Say hello and describe how you can help.');
  const mcpHealth = useAgentMcpHealthCheck();
  const testRun = useAgentTestRun();
  const agentAssets = useAgentAssets(agent?.id);
  const panelClassName = cn(
    'h-full shrink-0 overflow-y-auto bg-white p-5 scrollbar-thin dark:bg-slate-900',
    presentation === 'desktop'
      ? 'hidden w-80 border-l border-slate-200 dark:border-slate-800 xl:block'
      : 'block w-full',
  );

  useEffect(() => {
    setEditingAsset(null);
    setAssetEditError('');
    setTestPrompt('Say hello and describe how you can help.');
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

  const knowledge = readConfigItems<AgentKnowledgeRef>(agent.config, 'knowledge');
  const skills = readConfigItems<AgentSkillRef>(agent.config, 'skills');
  const canManageAssets = !agent.is_builtin;

  async function handleKnowledgeFile(file: File | undefined) {
    if (!agent || !file) return;
    setAssetError('');
    try {
      await agentAssets.uploadKnowledge.mutateAsync({
        agentId: agent.id,
        file,
        label: file.name,
        usage: knowledgeUsage,
      });
    } catch (error) {
      setAssetError(extractApiError(error));
    } finally {
      if (knowledgeInputRef.current) knowledgeInputRef.current.value = '';
    }
  }

  async function handleSkillFile(file: File | undefined) {
    if (!agent || !file) return;
    setAssetError('');
    try {
      await agentAssets.uploadSkill.mutateAsync({
        agentId: agent.id,
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

  async function deleteKnowledge(uploadId: string) {
    if (!agent) return;
    if (!window.confirm('仅从该 Agent 解除绑定，原始上传文件仍会保留。继续？')) return;
    setAssetError('');
    try {
      await agentAssets.deleteKnowledge.mutateAsync({ agentId: agent.id, uploadId });
    } catch (error) {
      setAssetError(extractApiError(error));
    }
  }

  async function deleteSkill(skillId: string) {
    if (!agent) return;
    if (!window.confirm('仅从该 Agent 解除绑定，原始上传文件仍会保留。继续？')) return;
    setAssetError('');
    try {
      await agentAssets.deleteSkill.mutateAsync({ agentId: agent.id, skillId });
    } catch (error) {
      setAssetError(extractApiError(error));
    }
  }

  async function editKnowledge(item: AgentKnowledgeRef) {
    setAssetEditError('');
    setEditingAsset({ kind: 'knowledge', item });
  }

  async function editSkill(item: AgentSkillRef) {
    setAssetEditError('');
    setEditingAsset({ kind: 'skill', item });
  }

  async function submitAssetEdit(input: AssetEditInput) {
    if (!agent || !editingAsset) return;
    setAssetError('');
    setAssetEditError('');
    try {
      if (editingAsset.kind === 'knowledge') {
        await agentAssets.updateKnowledge.mutateAsync({
          agentId: agent.id,
          uploadId: editingAsset.item.upload_id,
          label: input.label,
          usage: input.usage,
        });
      } else {
        await agentAssets.updateSkill.mutateAsync({
          agentId: agent.id,
          skillId: editingAsset.item.skill_id,
          name: input.name,
          description: input.description,
        });
      }
      setEditingAsset(null);
    } catch (error) {
      setAssetEditError(extractApiError(error));
    }
  }

  async function checkMcpHealth() {
    if (!agent) return;
    try {
      await mcpHealth.mutateAsync(agent.id);
    } catch {
      // Mutation state renders the failure; keep the panel open.
    }
  }

  async function runAgentTest() {
    if (!agent || !testPrompt.trim()) return;
    try {
      await testRun.mutateAsync({ agentId: agent.id, prompt: testPrompt.trim() });
    } catch {
      // Mutation state renders the failure; keep the panel open.
    }
  }

  const builderProfile = readBuilderProfile(agent.config);
  const permissions = readPermissions(agent.config);

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
      <div className="rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
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
              我的 Agent
            </>
          )}
        </div>

        {!agent.is_builtin && (
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
              disabled={isDeleting}
              onClick={() => onDelete?.(agent)}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-rose-300 px-3 py-2 text-sm text-rose-700 transition hover:bg-rose-50 hover:text-rose-800 disabled:cursor-not-allowed disabled:opacity-50 dark:border-rose-500/30 dark:text-rose-300 dark:hover:bg-rose-500/10 dark:hover:text-rose-100"
            >
              {isDeleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              删除
            </button>
          </div>
        )}
      </div>

      <section className="mt-5">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-500">
          能力
        </h3>
        <div className="flex flex-wrap gap-2">
          {agent.capabilities.map((capability) => (
            <span
              key={capability}
              className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-300"
            >
              {capability}
            </span>
          ))}
        </div>
      </section>

      <AgentConfigOverview profile={builderProfile} permissions={permissions} />

      <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
          <Code2 className="h-4 w-4 text-brand dark:text-brand-light" />
          运行配置
        </div>
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-xs text-slate-600 dark:text-slate-500">模型账号</dt>
            <dd className="mt-1 text-slate-800 dark:text-slate-200">
              {modelProfileSummary(readModelProfile(agent.config))}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-600 dark:text-slate-500">Model</dt>
            <dd className="mt-1 text-slate-800 dark:text-slate-200">
              {String(agent.config.model ?? 'default')}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-600 dark:text-slate-500">Temperature</dt>
            <dd className="mt-1 text-slate-800 dark:text-slate-200">
              {String(agent.config.temperature ?? 'default')}
            </dd>
          </div>
        </dl>
      </section>

      <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <AssetSectionHeader
          icon={FileText}
          title="知识文件"
          canManage={canManageAssets}
          isPending={agentAssets.isPending}
          actionLabel="上传 MD"
          onAction={() => knowledgeInputRef.current?.click()}
        />
        <input
          ref={knowledgeInputRef}
          type="file"
          accept=".md,.markdown,.txt,text/markdown,text/plain"
          className="hidden"
          onChange={(event) => void handleKnowledgeFile(event.currentTarget.files?.[0])}
        />
        {canManageAssets && (
          <label className="mb-3 block">
            <span className="text-xs font-medium text-slate-600 dark:text-slate-500">知识用途</span>
            <select
              value={knowledgeUsage}
              onChange={(event) => setKnowledgeUsage(event.target.value as AgentKnowledgeUsage)}
              className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-brand dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200"
            >
              {KNOWLEDGE_USAGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        )}
        <AssetList
          emptyText={
            canManageAssets ? '上传 Markdown 后会作为该 Agent 的显式知识。' : '暂无知识文件。'
          }
          items={knowledge.map((item) => ({
            id: item.upload_id,
            title: item.label || item.filename,
            meta: `${item.usage} · ${item.filename} · ${formatBytes(item.size_bytes)}`,
            downloadUploadId: item.upload_id,
            raw: item,
          }))}
          canDelete={canManageAssets}
          canEdit={canManageAssets}
          isPending={agentAssets.isPending}
          onDelete={deleteKnowledge}
          onEdit={(item) => void editKnowledge(item.raw as AgentKnowledgeRef)}
        />
      </section>

      <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <AssetSectionHeader
          icon={Wrench}
          title="Skills"
          canManage={canManageAssets}
          isPending={agentAssets.isPending}
          actionLabel="上传 Skill"
          onAction={() => skillInputRef.current?.click()}
        />
        <input
          ref={skillInputRef}
          type="file"
          accept=".md,.markdown,text/markdown"
          className="hidden"
          onChange={(event) => void handleSkillFile(event.currentTarget.files?.[0])}
        />
        {canManageAssets && (
          <div className="mb-3 space-y-3">
            <label className="block">
              <span className="text-xs font-medium text-slate-600 dark:text-slate-500">
                Skill 名称
              </span>
              <input
                value={skillName}
                onChange={(event) => setSkillName(event.target.value)}
                placeholder="留空时从 frontmatter 或标题解析"
                className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none placeholder:text-slate-500 focus:border-brand dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:placeholder:text-slate-600"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-600 dark:text-slate-500">
                Skill 描述
              </span>
              <textarea
                value={skillDescription}
                onChange={(event) => setSkillDescription(event.target.value)}
                rows={2}
                placeholder="说明这个 skill 什么时候应该被使用"
                className="mt-2 w-full resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-5 text-slate-950 outline-none placeholder:text-slate-500 focus:border-brand dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:placeholder:text-slate-600"
              />
            </label>
            <p className="text-xs leading-5 text-slate-600 dark:text-slate-500">
              若 Markdown 没有 name/description frontmatter，请在这里补充，否则后端会拒绝导入。
            </p>
          </div>
        )}
        <AssetList
          emptyText={canManageAssets ? '上传 SKILL.md 或 Markdown skill 定义。' : '暂无 Skills。'}
          items={skills.map((item) => ({
            id: item.skill_id,
            title: item.name,
            meta: `${item.description} · ${item.filename} · ${formatBytes(item.size_bytes)}`,
            downloadUploadId: item.upload_id,
            raw: item,
          }))}
          canDelete={canManageAssets}
          canEdit={canManageAssets}
          isPending={agentAssets.isPending}
          onDelete={deleteSkill}
          onEdit={(item) => void editSkill(item.raw as AgentSkillRef)}
        />
      </section>

      {assetError && (
        <div className="mt-4 rounded-md border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
          {assetError}
        </div>
      )}

      <AssetLifecycleSection
        bindingCount={agentAssets.assets.data?.bindings.length ?? knowledge.length + skills.length}
        historyTotal={agentAssets.history.data?.total ?? 0}
        usageTotal={agentAssets.usage.data?.total ?? 0}
        historyItems={agentAssets.history.data?.items ?? []}
        usageItems={agentAssets.usage.data?.items ?? []}
        isLoading={
          agentAssets.assets.isLoading ||
          agentAssets.history.isLoading ||
          agentAssets.usage.isLoading
        }
        hasError={Boolean(
          agentAssets.assets.error || agentAssets.history.error || agentAssets.usage.error,
        )}
      />

      <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
            <Wrench className="h-4 w-4 text-brand dark:text-brand-light" />
            MCP health
          </div>
          <button
            type="button"
            onClick={() => void checkMcpHealth()}
            disabled={mcpHealth.isPending}
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
          >
            {mcpHealth.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            Check
          </button>
        </div>
        {mcpHealth.data ? (
          <div className="space-y-2 text-sm text-slate-600 dark:text-slate-400">
            <div>Status: {mcpHealth.data.status}</div>
            {mcpHealth.data.servers.length ? (
              mcpHealth.data.servers.map((server) => (
                <div
                  key={server.name}
                  className="rounded-md border border-slate-300 p-2 dark:border-slate-800"
                >
                  <div className="text-slate-800 dark:text-slate-200">
                    {server.name} · {server.status}
                  </div>
                  {server.error ? (
                    <div className="mt-1 text-xs text-rose-700 dark:text-rose-300">
                      {server.error}
                    </div>
                  ) : null}
                  {server.tools.length ? (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {server.tools.map((tool) => (
                        <span
                          key={tool.name}
                          className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                        >
                          {tool.name}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <div className="text-xs text-slate-600 dark:text-slate-500">
                No MCP servers configured.
              </div>
            )}
          </div>
        ) : (
          <div className="text-sm text-slate-600 dark:text-slate-500">
            Run a check to verify configured MCP tools.
          </div>
        )}
      </section>

      <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
          <PlayCircle className="h-4 w-4 text-emerald-400" />
          Test run
        </div>
        <textarea
          value={testPrompt}
          onChange={(event) => setTestPrompt(event.target.value)}
          rows={3}
          className="w-full resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-5 text-slate-950 outline-none focus:border-brand dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200"
        />
        <button
          type="button"
          onClick={() => void runAgentTest()}
          disabled={testRun.isPending || !testPrompt.trim()}
          className="mt-3 inline-flex items-center gap-2 rounded-md bg-brand px-3 py-2 text-sm font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {testRun.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <PlayCircle className="h-4 w-4" />
          )}
          Run test
        </button>
        {testRun.data ? (
          <div className="mt-3 rounded-md border border-slate-300 bg-white p-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
            <div
              className={
                testRun.data.status === 'error'
                  ? 'text-rose-700 dark:text-rose-300'
                  : 'text-emerald-700 dark:text-emerald-300'
              }
            >
              {testRun.data.status}
            </div>
            <TestRunContent blocks={testRun.data.content} />
          </div>
        ) : null}
      </section>

      <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
          <MessageSquarePlus className="h-4 w-4 text-emerald-400" />
          接入状态
        </div>
        <div className="space-y-2 text-sm text-slate-700 dark:text-slate-400">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            远端 Agent 注册表已连接
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            可加入新建会话
          </div>
        </div>
      </section>

      <section className="mt-6">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-500">
          System Prompt
        </h3>
        <p className="rounded-md border border-slate-300 bg-slate-50 p-3 text-sm leading-6 text-slate-700 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-400">
          {agent.system_prompt ?? '该 Agent 使用默认系统提示。'}
        </p>
      </section>
      <AssetEditDialog
        editingAsset={editingAsset}
        error={assetEditError}
        isPending={agentAssets.updateKnowledge.isPending || agentAssets.updateSkill.isPending}
        onClose={() => setEditingAsset(null)}
        onSubmit={(input) => void submitAssetEdit(input)}
      />
    </aside>
  );
}

function AgentConfigOverview({
  profile,
  permissions,
}: {
  profile: AgentBuilderProfile | null;
  permissions: AgentPermissions | null;
}) {
  if (!profile && !permissions) return null;
  return (
    <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
        <Brain className="h-4 w-4 text-brand dark:text-brand-light" />
        Builder profile
      </div>
      <dl className="space-y-3 text-sm">
        {profile?.purpose ? <OverviewRow label="Purpose" value={profile.purpose} /> : null}
        {profile?.tone ? <OverviewRow label="Tone" value={profile.tone} /> : null}
        {profile?.clarification_policy ? (
          <OverviewRow label="Clarification" value={profile.clarification_policy} />
        ) : null}
        {permissions ? <OverviewRow label="Tools" value={permissionSummary(permissions)} /> : null}
      </dl>
    </section>
  );
}

function OverviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-600 dark:text-slate-500">{label}</dt>
      <dd className="mt-1 text-slate-800 dark:text-slate-200">{value}</dd>
    </div>
  );
}

function TestRunContent({ blocks }: { blocks: ContentBlock[] }) {
  const text = blocks
    .map((block) => (block.type === 'text' ? block.text : `[${block.type}]`))
    .filter(Boolean)
    .join('\n\n');
  if (!text) return null;
  return <div className="mt-2 whitespace-pre-wrap text-slate-700 dark:text-slate-300">{text}</div>;
}

function AssetLifecycleSection({
  bindingCount,
  historyTotal,
  usageTotal,
  historyItems,
  usageItems,
  isLoading,
  hasError,
}: {
  bindingCount: number;
  historyTotal: number;
  usageTotal: number;
  historyItems: AgentAssetVersionRef[];
  usageItems: AgentAssetUsageEventRef[];
  isLoading: boolean;
  hasError: boolean;
}) {
  return (
    <section className="mt-6 rounded-md border border-slate-300 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
          <Layers3 className="h-4 w-4 text-brand dark:text-brand-light" />
          资产生命周期
        </div>
        {isLoading && <Loader2 className="h-4 w-4 animate-spin text-slate-500" />}
      </div>
      <div className="grid grid-cols-3 gap-2">
        <LifecycleStat label="绑定" value={bindingCount} />
        <LifecycleStat label="版本" value={historyTotal} />
        <LifecycleStat label="使用" value={usageTotal} />
      </div>
      {hasError && (
        <p className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          资产记录接口暂不可用，上传和编辑功能仍可继续使用。
        </p>
      )}
      <div className="mt-4 space-y-4">
        <LifecycleList
          title="最近版本"
          emptyText="暂无版本历史。"
          items={historyItems.slice(0, 3).map((item) => ({
            id: item.id,
            title: `${versionActionLabel(item.action)} · v${item.version}`,
            meta: `${snapshotTitle(item.snapshot)} · ${formatDateTime(item.created_at)}`,
          }))}
        />
        <LifecycleList
          title="最近使用"
          emptyText="暂无注入记录。"
          items={usageItems.slice(0, 3).map((item) => ({
            id: item.id,
            title: `${usageStatusLabel(item.status)} · ${item.event_type}`,
            meta: `${item.reason || 'runtime context'} · ${formatDateTime(item.created_at)}`,
          }))}
        />
      </div>
    </section>
  );
}

function LifecycleStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-300 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-900/70">
      <div className="text-lg font-semibold text-slate-950 dark:text-white">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-slate-600 dark:text-slate-500">
        {label}
      </div>
    </div>
  );
}

function LifecycleList({
  title,
  emptyText,
  items,
}: {
  title: string;
  emptyText: string;
  items: Array<{ id: string; title: string; meta: string }>;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-500">
        <History className="h-3.5 w-3.5" />
        {title}
      </div>
      {items.length ? (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.id}
              className="rounded-md border border-slate-300 bg-white p-2 dark:border-slate-800 dark:bg-slate-900/50"
            >
              <div className="truncate text-xs font-medium text-slate-800 dark:text-slate-200">
                {item.title}
              </div>
              <div className="mt-1 truncate text-[11px] text-slate-600 dark:text-slate-500">
                {item.meta}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs leading-5 text-slate-600 dark:text-slate-500">{emptyText}</p>
      )}
    </div>
  );
}

function AssetSectionHeader({
  icon: Icon,
  title,
  canManage,
  isPending,
  actionLabel,
  onAction,
}: {
  icon: typeof FileText;
  title: string;
  canManage: boolean;
  isPending: boolean;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-sm font-medium text-slate-950 dark:text-white">
        <Icon className="h-4 w-4 text-brand dark:text-brand-light" />
        {title}
      </div>
      {canManage && (
        <button
          type="button"
          disabled={isPending}
          onClick={onAction}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
        >
          {isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <UploadCloud className="h-3.5 w-3.5" />
          )}
          {actionLabel}
        </button>
      )}
    </div>
  );
}

function AssetList({
  items,
  emptyText,
  canDelete,
  canEdit,
  isPending,
  onDelete,
  onEdit,
}: {
  items: Array<{
    id: string;
    title: string;
    meta: string;
    downloadUploadId?: string;
    raw?: unknown;
  }>;
  emptyText: string;
  canDelete: boolean;
  canEdit: boolean;
  isPending: boolean;
  onDelete: (id: string) => void | Promise<void>;
  onEdit?: (item: { id: string; title: string; meta: string; raw?: unknown }) => void;
}) {
  if (!items.length) {
    return <p className="text-sm leading-6 text-slate-600 dark:text-slate-500">{emptyText}</p>;
  }
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div
          key={item.id}
          className="flex items-start justify-between gap-3 rounded-md border border-slate-300 bg-white p-3 dark:border-slate-800 dark:bg-slate-900/70"
        >
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-slate-950 dark:text-slate-100">
              {item.title}
            </div>
            <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600 dark:text-slate-500">
              {item.meta}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {item.downloadUploadId && (
              <a
                href={uploadDownloadUrl(item.downloadUploadId)}
                className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                aria-label={`下载 ${item.title}`}
              >
                <Download className="h-4 w-4" />
              </a>
            )}
            {canEdit && onEdit && (
              <button
                type="button"
                disabled={isPending}
                onClick={() => onEdit(item)}
                className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                aria-label={`编辑 ${item.title}`}
              >
                <SquarePen className="h-4 w-4" />
              </button>
            )}
            {canDelete && (
              <button
                type="button"
                disabled={isPending}
                onClick={() => void onDelete(item.id)}
                className="shrink-0 rounded-md p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-rose-500/10 dark:hover:text-rose-300"
                aria-label={`从 Agent 解除绑定 ${item.title}`}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function AssetEditDialog({
  editingAsset,
  error,
  isPending,
  onClose,
  onSubmit,
}: {
  editingAsset: EditingAsset | null;
  error: string;
  isPending: boolean;
  onClose: () => void;
  onSubmit: (input: AssetEditInput) => void;
}) {
  const [label, setLabel] = useState('');
  const [usage, setUsage] = useState<AgentKnowledgeUsage>('reference');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [localError, setLocalError] = useState('');

  useEffect(() => {
    setLocalError('');
    if (!editingAsset) return;
    if (editingAsset.kind === 'knowledge') {
      setLabel(editingAsset.item.label || editingAsset.item.filename);
      setUsage(editingAsset.item.usage);
      return;
    }
    setName(editingAsset.item.name);
    setDescription(editingAsset.item.description);
  }, [editingAsset]);

  useEffect(() => {
    if (!editingAsset) return undefined;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape' && !isPending) onClose();
    }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [editingAsset, isPending, onClose]);

  if (!editingAsset) return null;

  const title = editingAsset.kind === 'knowledge' ? '编辑知识文件' : '编辑 Skill';
  const subtitle =
    editingAsset.kind === 'knowledge'
      ? '调整该 Agent 使用这份知识时的显示名称和用途。'
      : '调整该 Skill 在 Agent 配置中的名称和触发说明。';

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError('');
    if (editingAsset?.kind === 'knowledge') {
      const nextLabel = label.trim();
      if (!nextLabel) {
        setLocalError('知识文件显示名称不能为空。');
        return;
      }
      onSubmit({ label: nextLabel, usage });
      return;
    }
    const nextName = name.trim();
    const nextDescription = description.trim();
    if (!nextName || !nextDescription) {
      setLocalError('Skill 名称和描述都不能为空。');
      return;
    }
    onSubmit({ name: nextName, description: nextDescription });
  }

  return (
    <div
      className="fixed inset-0 z-[65] flex h-[100dvh] items-end bg-slate-950/80 backdrop-blur-sm sm:items-center sm:justify-center sm:px-4 sm:py-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="agent-asset-edit-title"
    >
      <form
        onSubmit={submit}
        className="native-mobile-sheet-shell flex max-h-[100dvh] w-full flex-col overflow-hidden border border-slate-300 bg-white shadow-2xl shadow-black/20 dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/40 sm:max-h-[calc(100dvh-3rem)] sm:max-w-lg sm:rounded-md"
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div className="min-w-0">
            <h2
              id="agent-asset-edit-title"
              className="text-base font-semibold text-slate-950 dark:text-white"
            >
              {title}
            </h2>
            <p className="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-500">{subtitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isPending}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-white"
            aria-label="关闭资产编辑"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5 scrollbar-thin">
          {editingAsset.kind === 'knowledge' ? (
            <>
              <label className="block">
                <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                  显示名称
                </span>
                <input
                  value={label}
                  maxLength={160}
                  onChange={(event) => setLabel(event.target.value)}
                  className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
                />
              </label>
              <label className="block">
                <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                  知识用途
                </span>
                <select
                  value={usage}
                  onChange={(event) => setUsage(event.target.value as AgentKnowledgeUsage)}
                  className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
                >
                  {KNOWLEDGE_USAGE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <p className="rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-500">
                原始文件：{editingAsset.item.filename}
              </p>
            </>
          ) : (
            <>
              <label className="block">
                <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                  Skill 名称
                </span>
                <input
                  value={name}
                  maxLength={160}
                  onChange={(event) => setName(event.target.value)}
                  className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
                />
              </label>
              <label className="block">
                <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                  Skill 描述
                </span>
                <textarea
                  value={description}
                  maxLength={240}
                  rows={4}
                  onChange={(event) => setDescription(event.target.value)}
                  className="mt-2 w-full resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-6 text-slate-950 outline-none focus:border-brand dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
                />
              </label>
              <p className="rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-500">
                原始文件：{editingAsset.item.filename}
              </p>
            </>
          )}

          {(localError || error) && (
            <div className="rounded-md border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
              {localError || error}
            </div>
          )}
        </div>

        <div className="flex shrink-0 justify-end gap-3 border-t border-slate-200 px-5 pb-[max(env(safe-area-inset-bottom),1rem)] pt-4 dark:border-slate-800">
          <button
            type="button"
            onClick={onClose}
            disabled={isPending}
            className="rounded-md px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-50 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={isPending}
            className="inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            保存
          </button>
        </div>
      </form>
    </div>
  );
}

function readBuilderProfile(config: Record<string, unknown>): AgentBuilderProfile | null {
  const value = config.builder_profile;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  return {
    role: optionalString(record.role),
    purpose: optionalString(record.purpose),
    goals: stringList(record.goals),
    tone: optionalString(record.tone),
    do_not_do: stringList(record.do_not_do),
    clarification_policy:
      record.clarification_policy === 'ask_first' ||
      record.clarification_policy === 'decide_with_defaults'
        ? record.clarification_policy
        : 'balanced',
    output_style: optionalString(record.output_style),
    starters: stringList(record.starters),
  };
}

function readPermissions(config: Record<string, unknown>): AgentPermissions | null {
  const value = config.permissions;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  return {
    workspace_read: record.workspace_read === true,
    workspace_write: record.workspace_write === true,
    run_commands:
      record.run_commands === 'ask' || record.run_commands === 'auto_low_risk'
        ? record.run_commands
        : 'never',
    network:
      record.network === 'ask' || record.network === 'allowlisted' ? record.network : 'never',
    deploy: record.deploy === 'ask' ? 'ask' : 'never',
    external_accounts: record.external_accounts === 'ask' ? 'ask' : 'never',
  };
}

function readModelProfile(config: Record<string, unknown>): AgentModelProfile | null {
  const value = config.model_profile;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  return {
    source: record.source === 'user_account' ? 'user_account' : 'agenthub_default',
    account_id: optionalString(record.account_id),
    provider:
      record.provider === 'deepseek' ||
      record.provider === 'openai' ||
      record.provider === 'anthropic' ||
      record.provider === 'openai_compatible'
        ? record.provider
        : null,
    model: optionalString(record.model),
  };
}

function modelProfileSummary(profile: AgentModelProfile | null): string {
  if (!profile || profile.source === 'agenthub_default') {
    return 'AgentHub 免费 DeepSeek';
  }
  return `${profile.provider ?? '自带 API'} · ${profile.model ?? '默认模型'}`;
}

function permissionSummary(permissions: AgentPermissions): string {
  const values: string[] = [];
  if (permissions.workspace_read || permissions.workspace_write) values.push('read files');
  if (permissions.workspace_write) values.push('write files');
  if (permissions.run_commands !== 'never') values.push('run commands');
  if (permissions.network !== 'never') values.push('network');
  if (permissions.deploy !== 'never') values.push('deploy on request');
  return values.length ? values.join(', ') : 'no tools';
}

function optionalString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    : [];
}

function readConfigItems<T>(config: Record<string, unknown>, key: string): T[] {
  const value = config[key];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is T => Boolean(item) && typeof item === 'object');
}

function formatBytes(size: number) {
  if (!Number.isFinite(size) || size <= 0) return '0 B';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function versionActionLabel(action: AgentAssetVersionRef['action']) {
  const labels: Record<AgentAssetVersionRef['action'], string> = {
    created: '创建',
    updated: '更新',
    unbound: '解除绑定',
    materialized: '迁移导入',
  };
  return labels[action] ?? action;
}

function usageStatusLabel(status: AgentAssetUsageEventRef['status']) {
  const labels: Record<AgentAssetUsageEventRef['status'], string> = {
    injected: '已注入',
    skipped: '已跳过',
    failed: '失败',
  };
  return labels[status] ?? status;
}

function snapshotTitle(snapshot: Record<string, unknown>) {
  const title = snapshot.name || snapshot.label || snapshot.filename || snapshot.kind;
  return typeof title === 'string' && title.trim() ? title : '资产记录';
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}
