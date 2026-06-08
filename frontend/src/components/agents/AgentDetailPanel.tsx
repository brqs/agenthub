import {
  Bot,
  CheckCircle2,
  Code2,
  Edit3,
  FileText,
  Loader2,
  MessageSquarePlus,
  ShieldCheck,
  Trash2,
  UploadCloud,
  Wrench,
  X,
} from 'lucide-react';
import { useRef, useState } from 'react';
import { AgentAvatar } from './AgentAvatar';
import { useAgentAssets } from '@/hooks/useAgentAssets';
import { extractApiError } from '@/lib/api';
import type { Agent, AgentKnowledgeRef, AgentSkillRef } from '@/lib/types';
import { cn } from '@/lib/utils';

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
  const agentAssets = useAgentAssets();
  const panelClassName = cn(
    'h-full shrink-0 overflow-y-auto bg-slate-900 p-5 scrollbar-thin',
    presentation === 'desktop' ? 'hidden w-80 border-l border-slate-800 xl:block' : 'block w-full',
  );

  if (!agent) {
    return (
      <aside className={panelClassName}>
        <div className="flex h-full items-center justify-center rounded-md border border-dashed border-slate-800 text-sm text-slate-500">
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
        usage: 'reference',
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
      await agentAssets.uploadSkill.mutateAsync({ agentId: agent.id, file });
    } catch (error) {
      setAssetError(extractApiError(error));
    } finally {
      if (skillInputRef.current) skillInputRef.current.value = '';
    }
  }

  async function deleteKnowledge(uploadId: string) {
    if (!agent) return;
    setAssetError('');
    try {
      await agentAssets.deleteKnowledge.mutateAsync({ agentId: agent.id, uploadId });
    } catch (error) {
      setAssetError(extractApiError(error));
    }
  }

  async function deleteSkill(skillId: string) {
    if (!agent) return;
    setAssetError('');
    try {
      await agentAssets.deleteSkill.mutateAsync({ agentId: agent.id, skillId });
    } catch (error) {
      setAssetError(extractApiError(error));
    }
  }

  return (
    <aside className={panelClassName}>
      {presentation === 'mobile' && (
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-white">Agent 详情</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white"
            aria-label="关闭 Agent 详情"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      <div className="rounded-md border border-slate-800 bg-slate-950/60 p-4">
        <div className="flex items-center gap-3">
          <AgentAvatar agent={agent} size="lg" />
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-white">{agent.name}</h2>
            <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">{agent.provider}</p>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2 text-sm text-slate-300">
          {agent.is_builtin ? (
            <>
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              内置 Agent
            </>
          ) : (
            <>
              <Bot className="h-4 w-4 text-brand-light" />
              我的 Agent
            </>
          )}
        </div>

        {!agent.is_builtin && (
          <div className="mt-4 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => onEdit?.(agent)}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-slate-800 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800 hover:text-white"
            >
              <Edit3 className="h-4 w-4" />
              编辑
            </button>
            <button
              type="button"
              disabled={isDeleting}
              onClick={() => onDelete?.(agent)}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-rose-500/30 px-3 py-2 text-sm text-rose-300 transition hover:bg-rose-500/10 hover:text-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
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
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">能力</h3>
        <div className="flex flex-wrap gap-2">
          {agent.capabilities.map((capability) => (
            <span
              key={capability}
              className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300"
            >
              {capability}
            </span>
          ))}
        </div>
      </section>

      <section className="mt-6 rounded-md border border-slate-800 bg-slate-950/60 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-white">
          <Code2 className="h-4 w-4 text-brand-light" />
          运行配置
        </div>
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-xs text-slate-500">Model</dt>
            <dd className="mt-1 text-slate-200">{String(agent.config.model ?? 'default')}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Temperature</dt>
            <dd className="mt-1 text-slate-200">{String(agent.config.temperature ?? 'default')}</dd>
          </div>
        </dl>
      </section>

      <section className="mt-6 rounded-md border border-slate-800 bg-slate-950/60 p-4">
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
        <AssetList
          emptyText={
            canManageAssets ? '上传 Markdown 后会作为该 Agent 的显式知识。' : '暂无知识文件。'
          }
          items={knowledge.map((item) => ({
            id: item.upload_id,
            title: item.label || item.filename,
            meta: `${item.usage} · ${item.filename} · ${formatBytes(item.size_bytes)}`,
          }))}
          canDelete={canManageAssets}
          isPending={agentAssets.isPending}
          onDelete={deleteKnowledge}
        />
      </section>

      <section className="mt-6 rounded-md border border-slate-800 bg-slate-950/60 p-4">
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
        <AssetList
          emptyText={canManageAssets ? '上传 SKILL.md 或 Markdown skill 定义。' : '暂无 Skills。'}
          items={skills.map((item) => ({
            id: item.skill_id,
            title: item.name,
            meta: `${item.description} · ${item.filename} · ${formatBytes(item.size_bytes)}`,
          }))}
          canDelete={canManageAssets}
          isPending={agentAssets.isPending}
          onDelete={deleteSkill}
        />
      </section>

      {assetError && (
        <div className="mt-4 rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
          {assetError}
        </div>
      )}

      <section className="mt-6 rounded-md border border-slate-800 bg-slate-950/60 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-white">
          <MessageSquarePlus className="h-4 w-4 text-emerald-400" />
          接入状态
        </div>
        <div className="space-y-2 text-sm text-slate-400">
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
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
          System Prompt
        </h3>
        <p className="rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm leading-6 text-slate-400">
          {agent.system_prompt ?? '该 Agent 使用默认系统提示。'}
        </p>
      </section>
    </aside>
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
      <div className="flex items-center gap-2 text-sm font-medium text-white">
        <Icon className="h-4 w-4 text-brand-light" />
        {title}
      </div>
      {canManage && (
        <button
          type="button"
          disabled={isPending}
          onClick={onAction}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
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
  isPending,
  onDelete,
}: {
  items: Array<{ id: string; title: string; meta: string }>;
  emptyText: string;
  canDelete: boolean;
  isPending: boolean;
  onDelete: (id: string) => void | Promise<void>;
}) {
  if (!items.length) {
    return <p className="text-sm leading-6 text-slate-500">{emptyText}</p>;
  }
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div
          key={item.id}
          className="flex items-start justify-between gap-3 rounded-md border border-slate-800 bg-slate-900/70 p-3"
        >
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-slate-100">{item.title}</div>
            <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{item.meta}</div>
          </div>
          {canDelete && (
            <button
              type="button"
              disabled={isPending}
              onClick={() => void onDelete(item.id)}
              className="shrink-0 rounded-md p-1.5 text-slate-500 hover:bg-rose-500/10 hover:text-rose-300 disabled:cursor-not-allowed disabled:opacity-50"
              aria-label={`删除 ${item.title}`}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      ))}
    </div>
  );
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
