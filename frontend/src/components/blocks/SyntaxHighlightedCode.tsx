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
}: {
  code: string;
  language: string;
  className?: string;
  fallbackClassName?: string;
}) {
  const theme = useUiStore((state) => state.theme);
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

  if (highlighted) {
    return (
      <div
        className={cn(
          'scrollbar-hidden overflow-auto [&_code]:break-normal [&_pre]:!m-0 [&_pre]:!min-w-max [&_pre]:!bg-transparent [&_pre]:!p-0',
          className,
        )}
        dangerouslySetInnerHTML={{ __html: highlighted }}
      />
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
