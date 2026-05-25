import { Sparkles } from 'lucide-react';

export const DEMO_PROMPT =
  '@orchestrator 帮我完成一个带任务拆解、代码产物、Diff 和网页预览的前端开发演示';

export function DemoPromptBar({ onSelect }: { onSelect: (prompt: string) => void }) {
  return (
    <div className="mb-3 flex items-center gap-3 rounded-md border border-brand/25 bg-brand/10 px-3 py-2">
      <div className="flex shrink-0 items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-light">
        <Sparkles className="h-3.5 w-3.5" />
        Demo
      </div>
      <button
        type="button"
        onClick={() => onSelect(DEMO_PROMPT)}
        className="min-w-0 flex-1 truncate rounded-md border border-slate-800 bg-slate-950/70 px-3 py-1.5 text-left text-sm text-slate-200 transition hover:border-brand/50 hover:bg-slate-900"
        aria-label={DEMO_PROMPT}
        title={DEMO_PROMPT}
      >
        {DEMO_PROMPT}
      </button>
    </div>
  );
}
