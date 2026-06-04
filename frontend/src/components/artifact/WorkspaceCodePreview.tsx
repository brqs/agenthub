import { Check, Copy, WrapText } from 'lucide-react';
import { useState } from 'react';
import { SyntaxHighlightedCode } from '@/components/blocks/SyntaxHighlightedCode';
import { cn } from '@/lib/utils';
import { inferWorkspaceCodeLanguage } from './workspaceCodeLanguage';

const MAX_HIGHLIGHT_BYTES = 200 * 1024;

function isLargeFile(code: string): boolean {
  return new Blob([code]).size > MAX_HIGHLIGHT_BYTES;
}

export function WorkspaceCodePreview({
  filename,
  mimeType,
  code,
  isFullscreen = false,
}: {
  filename: string;
  mimeType: string;
  code: string;
  isFullscreen?: boolean;
}) {
  const [wrapLines, setWrapLines] = useState(false);
  const [copied, setCopied] = useState(false);
  const language = inferWorkspaceCodeLanguage(filename, mimeType);
  const largeFile = isLargeFile(code);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section
      role="region"
      aria-label={`${filename} code preview`}
      className={cn(
        'min-h-0 border-t border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950',
        isFullscreen && 'flex flex-1 flex-col',
      )}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2 border-b border-slate-200 bg-white/70 px-3 py-2 text-xs dark:border-slate-800 dark:bg-slate-900/45">
        <span className="rounded-md border border-slate-200 bg-slate-100 px-2 py-0.5 font-medium uppercase tracking-wide text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
          {language}
        </span>
        {largeFile && (
          <span className="text-slate-500">文件较大，已使用纯文本模式以保证性能。</span>
        )}
        <span className="min-w-0 flex-1" />
        <button
          type="button"
          onClick={() => setWrapLines((value) => !value)}
          aria-pressed={wrapLines}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
        >
          <WrapText className="h-3.5 w-3.5" />
          {wrapLines ? '不换行' : '换行'}
        </button>
        <button
          type="button"
          onClick={() => void copyCode()}
          aria-label={copied ? '代码已复制' : '复制代码'}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      {largeFile ? (
        <PlainCodeFallback code={code} wrapLines={wrapLines} isFullscreen={isFullscreen} />
      ) : (
        <SyntaxHighlightedCode
          code={code}
          language={language}
          showLineNumbers
          wrapLines={wrapLines}
          className={cn(
            'text-xs leading-5',
            isFullscreen ? 'min-h-0 flex-1 [&_pre]:!p-3' : 'max-h-[36rem] [&_pre]:!p-3',
          )}
          fallbackClassName={cn(
            'text-xs leading-5',
            isFullscreen ? 'min-h-0 flex-1 p-3' : 'max-h-[36rem] p-3',
          )}
        />
      )}
    </section>
  );
}

function PlainCodeFallback({
  code,
  wrapLines,
  isFullscreen,
}: {
  code: string;
  wrapLines: boolean;
  isFullscreen: boolean;
}) {
  const lineNumbers = code.split('\n').map((_, index) => index + 1);
  return (
    <pre
      className={cn(
        'scrollbar-thin overflow-auto p-3 font-mono text-xs leading-5 text-slate-900 dark:text-slate-300',
        isFullscreen ? 'min-h-0 flex-1' : 'max-h-[36rem]',
      )}
    >
      <div className={cn('flex min-w-max', wrapLines && 'min-w-0')}>
        <ol
          aria-hidden="true"
          className="sticky left-0 z-10 select-none border-r border-slate-200 bg-slate-50/90 pr-3 text-right tabular-nums text-slate-400 dark:border-slate-800 dark:bg-slate-950/90 dark:text-slate-600"
        >
          {lineNumbers.map((line) => (
            <li key={line} className="min-w-8 pl-2">
              {line}
            </li>
          ))}
        </ol>
        <code className={cn('min-w-0 flex-1', wrapLines && 'whitespace-pre-wrap break-words')}>
          {code}
        </code>
      </div>
    </pre>
  );
}
