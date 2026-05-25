import { CodeBlock } from './CodeBlock';
import { TaskCardBlock } from './TaskCardBlock';
import { TextBlock } from './TextBlock';
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
          return (
            <div key={`${block.type}-${index}`} className="rounded-md border border-slate-700 bg-slate-950 p-3 text-sm">
              <div className="mb-2 text-xs text-slate-500">{block.filename}</div>
              <pre className="overflow-auto whitespace-pre-wrap font-mono text-slate-300">{block.after}</pre>
            </div>
          );
        }
        if (block.type === 'web_preview') {
          return (
            <a
              key={`${block.type}-${index}`}
              href={block.url}
              target="_blank"
              rel="noreferrer"
              className="block rounded-md border border-slate-700 bg-slate-950 p-3 text-sm text-brand-light hover:border-brand"
            >
              {block.title ?? block.url}
            </a>
          );
        }
        return (
          <div key={`${block.type}-${index}`} className="rounded-md border border-slate-700 bg-slate-950 p-3 text-sm text-slate-400">
            {block.filename}
          </div>
        );
      })}
    </div>
  );
}
