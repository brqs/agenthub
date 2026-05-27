import { renderToString } from 'katex';
import { isValidElement, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import type { Agent } from '@/lib/types';

const FENCED_CODE_PATTERN = /(```[\s\S]*?```|~~~[\s\S]*?~~~)/g;
const INLINE_CODE_PATTERN = /(`+[^`\n]*?`+)/g;
const AGENT_MENTION_HASH_PREFIX = '#agent-mention-';

function normalizeMathOutsideCode(text: string, streaming: boolean): string {
  return stabilizeStreamingMath(text, streaming)
    .replace(/\\\[((?:.|\n)*?)\\\]/g, (_match, content: string) => {
      return `\n\n$$\n${content.trim()}\n$$\n\n`;
    })
    .replace(/\\\(((?:.|\n)*?)\\\)/g, (_match, content: string) => `$${content}$`);
}

function normalizeAgentMentionsOutsideCode(text: string, mentionableAgentIds: Set<string>): string {
  if (mentionableAgentIds.size === 0) return text;

  return text.replace(
    /(^|[^\w-])@([A-Za-z0-9][A-Za-z0-9_-]*)/g,
    (match, prefix: string, agentId: string) => {
      if (!mentionableAgentIds.has(agentId)) return match;
      return `${prefix}[@${agentId}](${AGENT_MENTION_HASH_PREFIX}${agentId})`;
    },
  );
}

function normalizeInlineSegments(
  text: string,
  streaming: boolean,
  mentionableAgentIds: Set<string>,
): string {
  return text
    .split(INLINE_CODE_PATTERN)
    .map((segment, index) => {
      if (index % 2 === 1) return segment;
      return normalizeAgentMentionsOutsideCode(
        normalizeMathOutsideCode(segment, streaming),
        mentionableAgentIds,
      );
    })
    .join('');
}

function normalizeMarkdownForChat(
  text: string,
  streaming: boolean,
  mentionableAgentIds: Set<string>,
): string {
  return text
    .split(FENCED_CODE_PATTERN)
    .map((segment, index) => {
      if (index % 2 === 1) return segment;
      return normalizeInlineSegments(segment, streaming, mentionableAgentIds);
    })
    .join('');
}

function stabilizeStreamingMath(text: string, streaming: boolean): string {
  if (!streaming) return text;

  const tokens = [...text.matchAll(/(?<!\\)\${1,2}/g)];
  let inlineOpenIndex: number | null = null;
  let displayOpenIndex: number | null = null;

  for (const token of tokens) {
    const delimiter = token[0];
    const index = token.index;
    if (index === undefined) continue;

    if (delimiter === '$$') {
      displayOpenIndex = displayOpenIndex === null ? index : null;
      continue;
    }

    if (displayOpenIndex !== null) continue;
    inlineOpenIndex = inlineOpenIndex === null ? index : null;
  }

  const orphanIndex = displayOpenIndex ?? inlineOpenIndex;
  if (orphanIndex === null) return text;

  const delimiterLength = displayOpenIndex === null ? 1 : 2;
  return `${text.slice(0, orphanIndex)}${'\\$'.repeat(delimiterLength)}${text.slice(
    orphanIndex + delimiterLength,
  )}`;
}

function classNameHasMath(className: string | undefined): boolean {
  return className?.split(/\s+/).includes('language-math') ?? false;
}

function classNameHasDisplayMath(className: string | undefined): boolean {
  return className?.split(/\s+/).includes('math-display') ?? false;
}

function childrenToText(children: ReactNode): string {
  if (children === null || children === undefined || typeof children === 'boolean') return '';
  if (typeof children === 'string' || typeof children === 'number') return String(children);
  if (Array.isArray(children)) return children.map(childrenToText).join('');
  if (isValidElement<{ children?: ReactNode }>(children)) {
    return childrenToText(children.props.children);
  }
  return '';
}

function renderMathHtml(value: string, displayMode: boolean): string {
  return renderToString(value.trim(), {
    displayMode,
    output: 'html',
    strict: false,
    throwOnError: false,
    trust: false,
  });
}

/*
 * Per-node Tailwind classes for markdown rendering.
 *
 * Why not a parent `.markdown-text` class with descendant selectors?
 * react-markdown v9 dropped the `className` prop, and putting `.markdown-text`
 * on a wrapper div made every `.markdown-text .katex ...` rule active — which
 * inadvertently interfered with KaTeX's internal `vlist` / `inline-table`
 * positioning and broke sub/superscript layout for inline math.
 *
 * Mapping classes here keeps markdown styling per-element and lets KaTeX own
 * its own DOM layout entirely.
 */
const components: Components = {
  h1: ({ node: _node, ...props }) => (
    <h1 className="mt-4 mb-2 text-lg font-semibold text-white" {...props} />
  ),
  h2: ({ node: _node, ...props }) => (
    <h2 className="mt-4 mb-2 text-base font-semibold text-white" {...props} />
  ),
  h3: ({ node: _node, ...props }) => (
    <h3 className="mt-3 mb-2 text-sm font-semibold text-white" {...props} />
  ),
  h4: ({ node: _node, ...props }) => (
    <h4 className="mt-3 mb-2 text-sm font-semibold text-white" {...props} />
  ),
  p: ({ node: _node, ...props }) => <p className="my-2 leading-7" {...props} />,
  ul: ({ node: _node, ...props }) => (
    <ul className="my-2 list-disc space-y-1 pl-5 leading-7" {...props} />
  ),
  ol: ({ node: _node, ...props }) => (
    <ol className="my-2 list-decimal space-y-1 pl-5 leading-7" {...props} />
  ),
  li: ({ node: _node, ...props }) => <li className="leading-7" {...props} />,
  hr: ({ node: _node, ...props }) => (
    <hr className="my-3 border-slate-700" {...props} />
  ),
  blockquote: ({ node: _node, ...props }) => (
    <blockquote
      className="my-3 border-l-2 border-brand/50 pl-3 text-slate-400"
      {...props}
    />
  ),
  table: ({ node: _node, ...props }) => (
    <div className="my-3 max-w-full overflow-x-auto">
      <table
        className="w-max min-w-full border-collapse rounded-md border border-slate-800 text-sm"
        {...props}
      />
    </div>
  ),
  thead: ({ node: _node, ...props }) => <thead className="bg-slate-950/70" {...props} />,
  th: ({ node: _node, ...props }) => (
    <th
      className="border border-slate-800 bg-slate-950/70 px-3 py-2 text-left font-semibold text-slate-200"
      {...props}
    />
  ),
  td: ({ node: _node, ...props }) => (
    <td className="border border-slate-800 px-3 py-2 align-top" {...props} />
  ),
  pre: ({ node: _node, children, ...props }) => {
    if (
      isValidElement<{ className?: string }>(children) &&
      classNameHasDisplayMath(children.props.className)
    ) {
      return <>{children}</>;
    }

    return (
      <pre
        className="my-3 max-w-full overflow-x-auto rounded-md border border-slate-800 bg-slate-950 p-3 text-sm leading-6 text-slate-100"
        {...props}
      >
        {children}
      </pre>
    );
  },
  code: ({ node: _node, className, children, ...props }) => {
    if (classNameHasMath(className)) {
      const math = childrenToText(children);
      const displayMode = classNameHasDisplayMath(className);
      const Tag = displayMode ? 'div' : 'span';

      return (
        <Tag
          className={displayMode ? 'my-3 max-w-full overflow-x-auto overflow-y-visible' : undefined}
          dangerouslySetInnerHTML={{ __html: renderMathHtml(math, displayMode) }}
        />
      );
    }

    const isInline = !className || !className.startsWith('language-');
    if (isInline) {
      return (
        <code
          className="rounded bg-slate-950 px-1.5 py-0.5 font-mono text-brand-light"
          {...props}
        >
          {children}
        </code>
      );
    }
    return (
      <code className={`${className ?? ''} font-mono`} {...props}>
        {children}
      </code>
    );
  },
  a: ({ node: _node, href, children, ...props }) => {
    if (href?.startsWith(AGENT_MENTION_HASH_PREFIX)) {
      return (
        <span
          className="inline font-semibold text-current underline decoration-current/45 decoration-2 underline-offset-4"
          data-agent-mention={href.slice(AGENT_MENTION_HASH_PREFIX.length)}
          {...props}
        >
          {children}
        </span>
      );
    }

    return (
      <a
        className="text-brand-light underline-offset-2 hover:underline"
        target="_blank"
        rel="noreferrer"
        href={href}
        {...props}
      >
        {children}
      </a>
    );
  },
  strong: ({ node: _node, ...props }) => (
    <strong className="font-semibold text-white" {...props} />
  ),
};

export function TextBlock({
  text,
  streaming = false,
  agents = [],
}: {
  text: string;
  streaming?: boolean;
  agents?: Agent[];
}) {
  const normalizedText = normalizeMarkdownForChat(
    text,
    streaming,
    new Set(agents.map((agent) => agent.id)),
  );

  return (
    <div className={`agent-markdown min-w-0 text-slate-100${streaming ? ' streaming-cursor' : ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, [remarkMath, { singleDollarTextMath: true }]]}
        components={components}
      >
        {normalizedText}
      </ReactMarkdown>
    </div>
  );
}
