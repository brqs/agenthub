import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, ListChecks } from 'lucide-react';
import { ClarificationCard } from './ClarificationCard';
import { AttachmentBlock } from './AttachmentBlock';
import { CodeBlock } from './CodeBlock';
import { DeploymentStatusBlock } from './DeploymentStatusBlock';
import { DiffBlock } from './DiffBlock';
import { FileBlock } from './FileBlock';
import { ProcessBlock } from './ProcessBlock';
import { TaskCardBlock } from './TaskCardBlock';
import { TextBlock } from './TextBlock';
import { ToolCallBlock } from './ToolCallBlock';
import { TurnControlBlock } from './TurnControlBlock';
import { UnknownBlock } from './UnknownBlock';
import { WebPreviewBlock } from './WebPreviewBlock';
import { WorkflowBlock } from './WorkflowBlock';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import { buildRichArtifactViewModel } from '@/components/artifact/richArtifactModel';
import type { WorkspaceArtifact } from '@/lib/adapters/workspaces';
import type { DemoContentBlock } from '@/lib/mockData';
import type {
  Agent,
  FileBlock as FileContentBlock,
  PresentationMetadata,
} from '@/lib/types';

export function ContentRenderer({
  blocks,
  agents = [],
  streaming = false,
  conversationId,
  artifactManifestByPath,
}: {
  blocks: DemoContentBlock[];
  agents?: Agent[];
  streaming?: boolean;
  conversationId?: string;
  artifactManifestByPath?: Map<string, WorkspaceArtifact>;
}) {
  const groups = groupBlocksByAgent(blocks);
  const shouldGroup = new Set(groups.map((group) => group.agentId).filter(Boolean)).size > 1;

  return (
    <div className="mobile-text-safe space-y-2">
      {shouldGroup
        ? groups.map((group) => {
            if (!group.agentId) {
              return renderPresentationItems(
                group.blocks,
                blocks.length,
                agents,
                streaming,
                conversationId,
                artifactManifestByPath,
              );
            }

            const agent = agents.find((item) => item.id === group.agentId);
            return (
              <section
                key={`${group.agentId}-${group.blocks[0]?.index ?? 0}`}
                className="mobile-text-safe border-l-2 border-brand/40 pl-3"
              >
                <div className="mb-2 flex min-w-0 items-center gap-2 text-xs font-medium text-slate-600 dark:text-slate-300">
                  <AgentAvatar agent={agent} size="sm" />
                  <span className="truncate">{agent?.name ?? group.agentId}</span>
                </div>
                <div className="mobile-text-safe space-y-2">
                  {renderPresentationItems(
                    group.blocks,
                    blocks.length,
                    agents,
                    streaming,
                    conversationId,
                    artifactManifestByPath,
                  )}
                </div>
              </section>
            );
          })
        : renderPresentationItems(
            blocks.map((block, index) => ({ block, index })),
            blocks.length,
            agents,
            streaming,
            conversationId,
            artifactManifestByPath,
          )}
    </div>
  );
}

type IndexedBlock = { block: DemoContentBlock; index: number };

type PresentationItem =
  | {
      type: 'execution_group';
      groupId: string;
      label: string;
      blocks: IndexedBlock[];
    }
  | { type: 'block'; block: DemoContentBlock; index: number };

function renderPresentationItems(
  indexedBlocks: IndexedBlock[],
  blockCount: number,
  agents: Agent[],
  streaming: boolean,
  conversationId?: string,
  artifactManifestByPath?: Map<string, WorkspaceArtifact>,
) {
  return groupPresentationItems(indexedBlocks).map((item) => {
    if (item.type === 'block') {
      return renderBlock(
        item.block,
        item.index,
        blockCount,
        agents,
        streaming,
        conversationId,
        artifactManifestByPath,
      );
    }
    return (
      <ExecutionGroup
        key={`execution-${item.groupId}-${item.blocks[0]?.index ?? 0}`}
        item={item}
        blockCount={blockCount}
        agents={agents}
        streaming={streaming}
        conversationId={conversationId}
        artifactManifestByPath={artifactManifestByPath}
      />
    );
  });
}

function groupPresentationItems(indexedBlocks: IndexedBlock[]): PresentationItem[] {
  const items: PresentationItem[] = [];
  let currentGroup: Extract<PresentationItem, { type: 'execution_group' }> | null = null;

  const flushGroup = () => {
    if (currentGroup) {
      items.push(currentGroup);
      currentGroup = null;
    }
  };

  for (const item of indexedBlocks) {
    const presentation = blockPresentation(item.block);
    if (isCollapsibleExecutionBlock(item.block)) {
      const groupId = presentation?.group_id || 'execution-main';
      const label = presentation?.label || executionGroupLabel(item.block);
      if (!currentGroup || currentGroup.groupId !== groupId) {
        flushGroup();
        currentGroup = {
          type: 'execution_group',
          groupId,
          label,
          blocks: [],
        };
      }
      currentGroup.blocks.push(item);
      continue;
    }
    flushGroup();
    items.push({ type: 'block', block: item.block, index: item.index });
  }

  flushGroup();
  return items;
}

function ExecutionGroup({
  item,
  blockCount,
  agents,
  streaming,
  conversationId,
  artifactManifestByPath,
}: {
  item: Extract<PresentationItem, { type: 'execution_group' }>;
  blockCount: number;
  agents: Agent[];
  streaming: boolean;
  conversationId?: string;
  artifactManifestByPath?: Map<string, WorkspaceArtifact>;
}) {
  const [userChanged, setUserChanged] = useState(false);
  const [collapsed, setCollapsed] = useState(!streaming);
  const visibleStatus = streaming ? '进行中' : '已折叠';
  const blockLabel = useMemo(() => executionGroupSummary(item), [item]);

  useEffect(() => {
    if (!userChanged) {
      setCollapsed(!streaming);
    }
  }, [streaming, userChanged]);

  return (
    <section className="rounded-md border border-slate-200 bg-slate-50/80 dark:border-slate-700 dark:bg-slate-900/40">
      <button
        type="button"
        className="flex w-full min-w-0 items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 transition hover:bg-white/70 dark:text-slate-200 dark:hover:bg-slate-800/70"
        onClick={() => {
          setUserChanged(true);
          setCollapsed((value) => !value);
        }}
      >
        {collapsed ? (
          <ChevronRight className="h-4 w-4 shrink-0 text-slate-500" />
        ) : (
          <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" />
        )}
        <ListChecks className="h-4 w-4 shrink-0 text-brand" />
        <span className="min-w-0 flex-1 truncate font-medium">{blockLabel}</span>
        <span className="shrink-0 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
          {item.blocks.length} 项
        </span>
        <span className="shrink-0 text-xs text-slate-500 dark:text-slate-400">{visibleStatus}</span>
      </button>
      {!collapsed && (
        <div className="mobile-text-safe space-y-2 border-t border-slate-200 p-3 dark:border-slate-700">
          {item.blocks.map(({ block, index }) =>
            renderBlock(
              block,
              index,
              blockCount,
              agents,
              streaming,
              conversationId,
              artifactManifestByPath,
            ),
          )}
        </div>
      )}
    </section>
  );
}

function renderBlock(
  block: DemoContentBlock,
  index: number,
  blockCount: number,
  agents: Agent[],
  streaming: boolean,
  conversationId?: string,
  artifactManifestByPath?: Map<string, WorkspaceArtifact>,
) {
  if (block.type === 'text') {
    return (
      <TextBlock
        key={`${block.type}-${index}`}
        text={block.text}
        agents={agents}
        streaming={streaming && index === blockCount - 1}
      />
    );
  }
  if (block.type === 'code') {
    return <CodeBlock key={`${block.type}-${index}`} language={block.language} code={block.code} />;
  }
  if (block.type === 'task_card') {
    return <TaskCardBlock key={`${block.type}-${index}`} block={block} agents={agents} />;
  }
  if (block.type === 'process') {
    return <ProcessBlock key={`${block.type}-${index}`} block={block} />;
  }
  if (block.type === 'clarification') {
    return <ClarificationCard key={`${block.type}-${index}`} block={block} />;
  }
  if (block.type === 'attachment') {
    return <AttachmentBlock key={`${block.type}-${block.upload_id}`} block={block} />;
  }
  if (block.type === 'turn_control') {
    return <TurnControlBlock key={`${block.type}-${block.control_id ?? index}`} block={block} />;
  }
  if (block.type === 'tool_call') {
    return <ToolCallBlock key={`${block.type}-${block.call_id}`} block={block} />;
  }
  if (block.type === 'workflow') {
    return <WorkflowBlock key={`${block.type}-${index}`} block={block} />;
  }
  if (block.type === 'deployment_status') {
    return (
      <DeploymentStatusBlock
        key={`${block.type}-${block.deployment_id}`}
        block={block}
        conversationId={conversationId}
      />
    );
  }
  if (block.type === 'agent_switch') {
    const fromAgent = agents.find((agent) => agent.id === block.from_agent);
    const toAgent = agents.find((agent) => agent.id === block.to_agent);
    return (
      <div key={`${block.type}-${index}`} className="agent-switch-enter py-2">
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="h-px flex-1 bg-slate-800" />
          <span className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-md border border-brand/30 bg-brand/10 px-3 py-1 text-slate-300">
            <span className="truncate">{fromAgent?.name ?? block.from_agent}</span>
            <span className="text-brand-light">→</span>
            <span className="truncate">{toAgent?.name ?? block.to_agent}</span>
          </span>
          <span className="h-px flex-1 bg-slate-800" />
        </div>
        <div className="mx-auto mt-2 max-w-xl text-center text-xs leading-5 text-slate-500">
          {block.task}
        </div>
      </div>
    );
  }
  if (block.type === 'diff') {
    return (
      <DiffBlock
        key={`${block.type}-${index}`}
        filename={block.filename}
        before={block.before}
        after={block.after}
      />
    );
  }
  if (block.type === 'web_preview') {
    return (
      <WebPreviewBlock
        key={`${block.type}-${index}`}
        url={block.url}
        title={block.title}
        description={block.description}
        previewTitle={'preview_title' in block ? block.preview_title : undefined}
        previewBody={'preview_body' in block ? block.preview_body : undefined}
      />
    );
  }
  if (block.type === 'file') {
    const fileBlock = block as FileContentBlock;
    const model = buildRichArtifactViewModel(
      fileBlock,
      fileBlock.path ? artifactManifestByPath?.get(fileBlock.path) : null,
    );
    return (
      <FileBlock
        key={`${block.type}-${index}`}
        filename={model.filename}
        path={model.path}
        url={model.url}
        size={model.size}
        mimeType={model.mimeType}
        artifactKind={model.artifactKind}
        previewText={model.previewText}
        previewTruncated={model.previewTruncated}
        metadata={model.metadata}
        evaluationStatus={model.evaluationStatus}
        evaluationResults={model.evaluationResults}
        taskId={model.taskId}
        runId={model.runId}
      />
    );
  }
  const unknownBlock = block as { type?: string };
  return (
    <UnknownBlock
      key={`${unknownBlock.type ?? 'unknown'}-${index}`}
      type={unknownBlock.type ?? 'unknown'}
    />
  );
}

function blockPresentation(block: DemoContentBlock): PresentationMetadata | null {
  const presentation = (block as { presentation?: unknown }).presentation;
  if (!presentation || typeof presentation !== 'object') return null;
  const value = presentation as PresentationMetadata;
  return typeof value.role === 'string' ? value : null;
}

function isCollapsibleExecutionBlock(block: DemoContentBlock): boolean {
  const presentation = blockPresentation(block);
  if (presentation) {
    return presentation.collapsible === true;
  }
  return block.type === 'process' || block.type === 'tool_call' || block.type === 'agent_switch';
}

function executionGroupLabel(block: DemoContentBlock): string {
  if (block.type === 'process') return block.title || '执行过程';
  if (block.type === 'tool_call') return '工具调用';
  if (block.type === 'agent_switch') return 'Agent 切换';
  if (block.type === 'task_card') return block.title || '调度计划';
  if (block.type === 'deployment_status') return '部署证据';
  if (block.type === 'web_preview') return '预览证据';
  if (block.type === 'file') return '产物证据';
  return '执行过程';
}

function executionGroupSummary(
  item: Extract<PresentationItem, { type: 'execution_group' }>,
): string {
  const firstProcess = item.blocks.find(({ block }) => block.type === 'process')?.block;
  if (firstProcess?.type === 'process' && firstProcess.summary) {
    return firstProcess.summary;
  }
  return item.label;
}

function groupBlocksByAgent(blocks: DemoContentBlock[]) {
  const groups: Array<{
    agentId: string | null;
    blocks: Array<{ block: DemoContentBlock; index: number }>;
  }> = [];

  blocks.forEach((block, index) => {
    const agentId = blockAgentId(block);
    const current = groups[groups.length - 1];
    if (current && current.agentId === agentId) {
      current.blocks.push({ block, index });
      return;
    }
    groups.push({ agentId, blocks: [{ block, index }] });
  });

  return groups;
}

function blockAgentId(block: DemoContentBlock): string | null {
  const value = (block as { agent_id?: unknown }).agent_id;
  return typeof value === 'string' && value ? value : null;
}
