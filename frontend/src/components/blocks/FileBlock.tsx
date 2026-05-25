import { ExternalLink, Eye, FileArchive, FileCode2, FileText, FileType, X } from 'lucide-react';
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(mimeType: string) {
  if (mimeType.includes('zip') || mimeType.includes('tar')) return FileArchive;
  if (mimeType.includes('javascript') || mimeType.includes('typescript') || mimeType.includes('json')) return FileCode2;
  if (mimeType.includes('text') || mimeType.includes('markdown')) return FileText;
  return FileType;
}

export function FileBlock({
  filename,
  url,
  size,
  mimeType,
  previewText,
}: {
  filename: string;
  url: string;
  size: number;
  mimeType: string;
  previewText?: string;
}) {
  const Icon = getFileIcon(mimeType);
  const [previewOpen, setPreviewOpen] = useState(false);
  const canPreview = Boolean(previewText);

  return (
    <>
      <div className="my-3 flex items-center gap-3 rounded-md border border-slate-700 bg-slate-950 p-3 text-sm transition hover:border-brand hover:bg-slate-900">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-slate-900 text-brand-light">
          <Icon className="h-5 w-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium text-slate-100">{filename}</span>
          <span className="mt-1 block truncate text-xs text-slate-500">
            {mimeType} · {formatBytes(size)}
          </span>
        </span>
        {canPreview && (
          <button
            type="button"
            onClick={() => setPreviewOpen(true)}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-800 hover:text-white"
            title="预览文件"
          >
            <Eye className="h-4 w-4" />
          </button>
        )}
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-800 hover:text-white"
          title="打开外链"
        >
          <ExternalLink className="h-4 w-4" />
        </a>
      </div>

      {previewOpen && previewText && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 backdrop-blur-sm">
          <div className="flex max-h-[82vh] w-full max-w-3xl flex-col overflow-hidden rounded-md border border-slate-700 bg-slate-900 shadow-2xl shadow-black/40">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-white">{filename}</div>
                <div className="mt-1 text-xs text-slate-500">{mimeType} · {formatBytes(size)}</div>
              </div>
              <button
                type="button"
                onClick={() => setPreviewOpen(false)}
                className="rounded-md p-2 text-slate-500 hover:bg-slate-800 hover:text-white"
                title="关闭预览"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="min-h-0 overflow-y-auto bg-slate-950 p-6 scrollbar-thin">
              {mimeType.includes('markdown') ? (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  className="prose prose-invert max-w-none prose-p:leading-7 prose-li:my-1 prose-code:text-brand-light"
                >
                  {previewText}
                </ReactMarkdown>
              ) : (
                <pre className="whitespace-pre-wrap text-sm leading-6 text-slate-200">{previewText}</pre>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
