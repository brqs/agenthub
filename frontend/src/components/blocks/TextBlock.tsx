import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function TextBlock({ text, streaming = false }: { text: string; streaming?: boolean }) {
  return (
    <div className={streaming ? 'streaming-cursor' : undefined}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        className="prose prose-invert max-w-none prose-p:my-2 prose-pre:my-3 prose-code:text-brand-light"
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

