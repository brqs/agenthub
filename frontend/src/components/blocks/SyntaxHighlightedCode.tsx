import { useEffect, useState } from 'react';
import { createHighlighterCore, createJavaScriptRegexEngine } from 'shiki/core';
import bash from 'shiki/langs/bash.mjs';
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
import { cn } from '@/lib/utils';

type SupportedLanguage =
  | 'bash'
  | 'css'
  | 'html'
  | 'javascript'
  | 'json'
  | 'markdown'
  | 'tsx'
  | 'typescript'
  | 'yaml';

const SUPPORTED_LANGUAGES = new Set<string>([
  'bash',
  'css',
  'html',
  'javascript',
  'js',
  'json',
  'markdown',
  'md',
  'shell',
  'sh',
  'tsx',
  'typescript',
  'ts',
  'yaml',
  'yml',
]);

const highlighterPromise = createHighlighterCore({
  themes: [githubDark, githubLight],
  langs: [bash, css, html, javascript, json, markdown, tsx, typescript, yaml],
  engine: createJavaScriptRegexEngine(),
});

function normalizeLanguage(language: string): SupportedLanguage {
  const normalized = language.toLowerCase();
  if (!SUPPORTED_LANGUAGES.has(normalized)) return 'markdown';
  if (normalized === 'js') return 'javascript';
  if (normalized === 'ts') return 'typescript';
  if (normalized === 'md') return 'markdown';
  if (normalized === 'sh' || normalized === 'shell') return 'bash';
  if (normalized === 'yml') return 'yaml';
  return normalized as SupportedLanguage;
}

export function SyntaxHighlightedCode({
  code,
  language,
  className,
  fallbackClassName,
  showLineNumbers = false,
  wrapLines = false,
}: {
  code: string;
  language: string;
  className?: string;
  fallbackClassName?: string;
  showLineNumbers?: boolean;
  wrapLines?: boolean;
}) {
  const theme = useUiStore((state) => state.theme);
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const lineNumbers = code.split('\n').map((_, index) => index + 1);
  const codeClassName = cn(
    '[&_code]:break-normal [&_pre]:!m-0 [&_pre]:!min-w-max [&_pre]:!bg-transparent [&_pre]:!p-0',
    wrapLines && '[&_code]:!whitespace-pre-wrap [&_pre]:!min-w-0 [&_pre]:!whitespace-pre-wrap',
  );

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

  if (highlighted) {
    if (showLineNumbers) {
      return (
        <div className={cn('scrollbar-hidden overflow-auto', className)}>
          <div className={cn('flex min-w-max', wrapLines && 'min-w-0')}>
            <LineNumberGutter lineNumbers={lineNumbers} />
            <div
              className={cn('min-w-0 flex-1', codeClassName)}
              dangerouslySetInnerHTML={{ __html: highlighted }}
            />
          </div>
        </div>
      );
    }
    return (
      <div
        className={cn(
          'scrollbar-hidden overflow-auto',
          codeClassName,
          className,
        )}
        dangerouslySetInnerHTML={{ __html: highlighted }}
      />
    );
  }

  if (showLineNumbers) {
    return (
      <pre
        className={cn(
          'scrollbar-hidden min-w-0 overflow-auto text-slate-800 dark:text-slate-200',
          fallbackClassName,
        )}
      >
        <div className={cn('flex min-w-max', wrapLines && 'min-w-0')}>
          <LineNumberGutter lineNumbers={lineNumbers} />
          <code className={cn('min-w-0 flex-1 font-mono', wrapLines && 'whitespace-pre-wrap break-words')}>
            {code}
          </code>
        </div>
      </pre>
    );
  }

  return (
    <pre
      className={cn(
        'scrollbar-hidden min-w-0 overflow-auto text-slate-800 dark:text-slate-200',
        fallbackClassName,
      )}
    >
      <code className="font-mono">{code}</code>
    </pre>
  );
}

function LineNumberGutter({ lineNumbers }: { lineNumbers: number[] }) {
  return (
    <ol
      aria-hidden="true"
      className="sticky left-0 z-10 select-none border-r border-slate-200 bg-slate-100/85 pr-3 text-right tabular-nums text-slate-400 dark:border-slate-800 dark:bg-slate-950/85 dark:text-slate-600"
    >
      {lineNumbers.map((line) => (
        <li key={line} className="min-w-8 pl-2">
          {line}
        </li>
      ))}
    </ol>
  );
}
