import { Check, Copy } from 'lucide-react';
import { useState } from 'react';
import { SyntaxHighlightedCode } from './SyntaxHighlightedCode';

export function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

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
    <div className="my-3 min-w-0 overflow-hidden rounded-md border border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-950">
      <div className="flex items-center justify-between border-b border-slate-300 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-950">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-600 dark:text-slate-400">
          {language || 'text'}
        </span>
        <button
          type="button"
          onClick={copyCode}
          title={copied ? '代码已复制' : '复制代码'}
          aria-label={copied ? '代码已复制' : '复制代码'}
          className="flex items-center gap-1.5 rounded px-2 py-1 text-xs text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <SyntaxHighlightedCode
        code={code}
        language={language}
        className="max-h-80 text-sm leading-6 [&_pre]:!p-4"
        fallbackClassName="max-h-80 p-4 text-sm leading-6"
      />
    </div>
  );
}
