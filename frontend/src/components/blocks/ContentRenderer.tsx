import { ClarificationCard } from './ClarificationCard';
import { CodeBlock } from './CodeBlock';
import { DeploymentStatusBlock } from './DeploymentStatusBlock';
import { DiffBlock } from './DiffBlock';
import { FileBlock } from './FileBlock';
import { ProcessBlock } from './ProcessBlock';
import { TaskCardBlock } from './TaskCardBlock';
import { TextBlock } from './TextBlock';
import { ToolCallBlock } from './ToolCallBlock';
import { UnknownBlock } from './UnknownBlock';
import { WebPreviewBlock } from './WebPreviewBlock';
import { WorkflowBlock } from './WorkflowBlock';
import { AgentAvatar } from '@/components/agents/AgentAvatar';
import { buildRichArtifactViewModel } from '@/components/artifact/richArtifactModel';
import type { WorkspaceArtifact } from '@/lib/adapters/workspaces';
import type { DemoContentBlock } from '@/lib/mockData';
import type { Agent, FileBlock as FileContentBlock } from '@/lib/types';

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
              return group.blocks.map(({ block, index }) =>
                renderBlock(
                  block,
                  index,
                  blocks.length,
                  agents,
                  streaming,
                  conversationId,
                  artifactManifestByPath,
                ),
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
                  {group.blocks.map(({ block, index }) =>
                    renderBlock(
                      block,
                      index,
                      blocks.length,
                      agents,
                      streaming,
                      conversationId,
                      artifactManifestByPath,
                    ),
                  )}
                </div>
              </section>
            );
          })
        : blocks.map((block, index) =>
            renderBlock(
              block,
              index,
              blocks.length,
              agents,
              streaming,
              conversationId,
              artifactManifestByPath,
            ),
          )}
    </div>
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
