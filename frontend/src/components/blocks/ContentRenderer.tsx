import { CodeBlock } from './CodeBlock';
import { DiffBlock } from './DiffBlock';
import { FileBlock } from './FileBlock';
import { TaskCardBlock } from './TaskCardBlock';
import { TextBlock } from './TextBlock';
import { UnknownBlock } from './UnknownBlock';
import { WebPreviewBlock } from './WebPreviewBlock';
import type { DemoContentBlock } from '@/lib/mockData';
import { getAgent } from '@/lib/mockData';

export function ContentRenderer({
  blocks,
  streaming = false,
}: {
  blocks: DemoContentBlock[];
  streaming?: boolean;
}) {
  return (
    <div className="space-y-2">
      {blocks.map((block, index) => {
        if (block.type === 'text') {
          return (
            <TextBlock
              key={`${block.type}-${index}`}
              text={block.text}
              streaming={streaming && index === blocks.length - 1}
            />
          );
        }
        if (block.type === 'code') {
          return <CodeBlock key={`${block.type}-${index}`} language={block.language} code={block.code} />;
        }
        if (block.type === 'task_card') {
          return <TaskCardBlock key={`${block.type}-${index}`} block={block} />;
        }
        if (block.type === 'agent_switch') {
          const fromAgent = getAgent(block.from_agent);
          const toAgent = getAgent(block.to_agent);
          return (
            <div key={`${block.type}-${index}`} className="py-2">
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <span className="h-px flex-1 bg-slate-800" />
                <span className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1 text-slate-300">
                  {fromAgent?.name ?? block.from_agent} → {toAgent?.name ?? block.to_agent}
                </span>
                <span className="h-px flex-1 bg-slate-800" />
              </div>
              <div className="mt-2 text-center text-xs text-slate-500">{block.task}</div>
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
