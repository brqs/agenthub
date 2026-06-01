import { CodeBlock } from './CodeBlock';
import { DeploymentStatusBlock } from './DeploymentStatusBlock';
import { DiffBlock } from './DiffBlock';
import { FileBlock } from './FileBlock';
import { TaskCardBlock } from './TaskCardBlock';
import { TextBlock } from './TextBlock';
import { ToolCallBlock } from './ToolCallBlock';
import { UnknownBlock } from './UnknownBlock';
import { WebPreviewBlock } from './WebPreviewBlock';
import type { DemoContentBlock } from '@/lib/mockData';
import type { Agent } from '@/lib/types';

export function ContentRenderer({
  blocks,
  agents = [],
  streaming = false,
  conversationId,
}: {
  blocks: DemoContentBlock[];
  agents?: Agent[];
  streaming?: boolean;
  conversationId?: string;
}) {
  return (
    <div className="min-w-0 space-y-2">
      {blocks.map((block, index) => {
        if (block.type === 'text') {
          return (
            <TextBlock
              key={`${block.type}-${index}`}
              text={block.text}
              agents={agents}
              streaming={streaming && index === blocks.length - 1}
            />
          );
        }
        if (block.type === 'code') {
          return <CodeBlock key={`${block.type}-${index}`} language={block.language} code={block.code} />;
        }
        if (block.type === 'task_card') {
          return <TaskCardBlock key={`${block.type}-${index}`} block={block} agents={agents} />;
        }
        if (block.type === 'tool_call') {
          return <ToolCallBlock key={`${block.type}-${block.call_id}`} block={block} />;
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
              <div className="mx-auto mt-2 max-w-xl text-center text-xs leading-5 text-slate-500">{block.task}</div>
            </div>
          );
        }
        if (block.type === 'diff') {
          return <DiffBlock key={`${block.type}-${index}`} filename={block.filename} before={block.before} after={block.after} />;
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
          return (
            <FileBlock
              key={`${block.type}-${index}`}
              filename={block.filename}
              url={block.url}
              size={block.size}
              mimeType={block.mime_type}
              previewText={'preview_text' in block ? block.preview_text : undefined}
            />
          );
        }
        const unknownBlock = block as { type?: string };
        return (
          <UnknownBlock key={`${unknownBlock.type ?? 'unknown'}-${index}`} type={unknownBlock.type ?? 'unknown'} />
        );
      })}
    </div>
  );
}
