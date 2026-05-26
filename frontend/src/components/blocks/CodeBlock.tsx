import { Check, Copy } from 'lucide-react';
import { useEffect, useState } from 'react';
import { createHighlighterCore, createJavaScriptRegexEngine } from 'shiki/core';
import css from 'shiki/langs/css.mjs';
import html from 'shiki/langs/html.mjs';
import javascript from 'shiki/langs/javascript.mjs';
import json from 'shiki/langs/json.mjs';
import markdown from 'shiki/langs/markdown.mjs';
import tsx from 'shiki/langs/tsx.mjs';
import typescript from 'shiki/langs/typescript.mjs';
import yaml from 'shiki/langs/yaml.mjs';
import githubDark from 'shiki/themes/github-dark.mjs';
import githubLight from 'shiki/themes/github-light.mjs';
import { useUiStore } from '@/stores/uiStore';

type SupportedLanguage = 'css' | 'html' | 'javascript' | 'json' | 'markdown' | 'tsx' | 'typescript' | 'yaml';

const SUPPORTED_LANGUAGES = new Set<string>([
  'css',
  'html',
  'javascript',
  'js',
  'json',
  'markdown',
  'md',
  'tsx',
  'typescript',
  'ts',
  'yaml',
  'yml',
]);

const highlighterPromise = createHighlighterCore({
  themes: [githubDark, githubLight],
  langs: [css, html, javascript, json, markdown, tsx, typescript, yaml],
  engine: createJavaScriptRegexEngine(),
});

function normalizeLanguage(language: string): SupportedLanguage {
  const normalized = language.toLowerCase();
  if (!SUPPORTED_LANGUAGES.has(normalized)) return 'markdown';
  if (normalized === 'js') return 'javascript';
  if (normalized === 'ts') return 'typescript';
  if (normalized === 'md') return 'markdown';
  if (normalized === 'yml') return 'yaml';
  return normalized as SupportedLanguage;
}

export function CodeBlock({ language, code }: { language: string; code: string }) {
  const theme = useUiStore((state) => state.theme);
  const [copied, setCopied] = useState(false);
  const [highlighted, setHighlighted] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function highlight() {
      try {
        const highlighter = await highlighterPromise;
        const html = highlighter.codeToHtml(code, {
          lang: normalizeLanguage(language || 'markdown'),
          theme: theme === 'dark' ? 'github-dark' : 'github-light',
        });
        if (!cancelled) setHighlighted(html);
      } catch {
        if (!cancelled) setHighlighted(null);
      }
    }

    void highlight();

    return () => {
      cancelled = true;
    };
  }, [code, language, theme]);

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
      {highlighted ? (
        <div
          className="scrollbar-hidden max-h-80 overflow-auto text-sm leading-6 [&_code]:break-normal [&_pre]:!m-0 [&_pre]:!min-w-max [&_pre]:!bg-transparent [&_pre]:!p-4"
          dangerouslySetInnerHTML={{ __html: highlighted }}
        />
      ) : (
        <pre className="scrollbar-hidden max-h-80 min-w-0 overflow-auto p-4 text-sm leading-6 text-slate-800 dark:text-slate-200">
          <code className="font-mono">{code}</code>
        </pre>
      )}
    </div>
  );
}
