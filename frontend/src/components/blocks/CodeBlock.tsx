import { Check, Copy } from 'lucide-react';
import { useState } from 'react';

export function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <div className="my-3 overflow-hidden rounded-md border border-slate-700 bg-slate-950">
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          {language || 'text'}
        </span>
        <button
          type="button"
          onClick={copyCode}
          className="flex items-center gap-1.5 rounded px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-white"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="max-h-96 overflow-auto p-4 text-sm leading-6 text-slate-200 scrollbar-thin">
        <code className="font-mono">{code}</code>
      </pre>
    </div>
  );
}

