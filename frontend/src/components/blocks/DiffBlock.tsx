import { GitCompareArrows } from 'lucide-react';

interface DiffLine {
  type: 'context' | 'add' | 'remove';
  beforeLine: number | null;
  afterLine: number | null;
  text: string;
}

function buildUnifiedDiff(before: string, after: string): DiffLine[] {
  const beforeLines = before.split('\n');
  const afterLines = after.split('\n');
  const rows = beforeLines.length + 1;
  const columns = afterLines.length + 1;
  const dp = Array.from({ length: rows }, () => Array<number>(columns).fill(0));

  for (let i = beforeLines.length - 1; i >= 0; i -= 1) {
    for (let j = afterLines.length - 1; j >= 0; j -= 1) {
      dp[i][j] =
        beforeLines[i] === afterLines[j]
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const diff: DiffLine[] = [];
  let i = 0;
  let j = 0;
  let beforeLine = 1;
  let afterLine = 1;

  while (i < beforeLines.length || j < afterLines.length) {
    if (i < beforeLines.length && j < afterLines.length && beforeLines[i] === afterLines[j]) {
      diff.push({ type: 'context', beforeLine, afterLine, text: beforeLines[i] });
      i += 1;
      j += 1;
      beforeLine += 1;
      afterLine += 1;
    } else if (j < afterLines.length && (i === beforeLines.length || dp[i][j + 1] >= dp[i + 1][j])) {
      diff.push({ type: 'add', beforeLine: null, afterLine, text: afterLines[j] });
      j += 1;
      afterLine += 1;
    } else if (i < beforeLines.length) {
      diff.push({ type: 'remove', beforeLine, afterLine: null, text: beforeLines[i] });
      i += 1;
      beforeLine += 1;
    }
  }

  return diff;
}

const LINE_CLASS: Record<DiffLine['type'], string> = {
  context: 'bg-slate-950 text-slate-300',
  add: 'bg-emerald-950/40 text-emerald-100',
  remove: 'bg-red-950/40 text-red-100',
};

const PREFIX: Record<DiffLine['type'], string> = {
  context: ' ',
  add: '+',
  remove: '-',
};

export function DiffBlock({
  filename,
  before,
  after,
}: {
  filename: string;
  before: string;
  after: string;
}) {
  const diff = buildUnifiedDiff(before, after);

  return (
    <div className="my-3 overflow-hidden rounded-md border border-slate-700 bg-slate-950">
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <GitCompareArrows className="h-4 w-4 shrink-0 text-brand-light" />
          <span className="truncate text-xs font-medium text-slate-300">{filename}</span>
        </div>
        <span className="rounded bg-slate-900 px-2 py-1 text-xs text-slate-500">
          {diff.filter((line) => line.type === 'add').length} added / {diff.filter((line) => line.type === 'remove').length} removed
        </span>
      </div>
      <div className="max-h-96 overflow-auto text-sm scrollbar-thin">
        {diff.map((line, index) => (
          <div
            key={`${line.type}-${index}-${line.text}`}
            className={`grid grid-cols-[48px_48px_24px_1fr] border-b border-slate-900/80 font-mono leading-6 ${LINE_CLASS[line.type]}`}
          >
            <span className="select-none border-r border-slate-800 px-2 text-right text-xs text-slate-600">
              {line.beforeLine ?? ''}
            </span>
            <span className="select-none border-r border-slate-800 px-2 text-right text-xs text-slate-600">
              {line.afterLine ?? ''}
            </span>
            <span className="select-none px-2 text-center text-xs text-slate-500">{PREFIX[line.type]}</span>
            <span className="min-w-0 whitespace-pre px-2">{line.text || ' '}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
