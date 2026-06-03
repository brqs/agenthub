import {
  ExternalLink,
  Eye,
  FileArchive,
  FileCode2,
  FileImage,
  FileText,
  FileType,
  Presentation,
  X,
} from 'lucide-react';
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { handleExternalLink } from '@/lib/nativeShell';

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(mimeType: string) {
  if (mimeType.includes('zip') || mimeType.includes('tar')) return FileArchive;
  if (mimeType.startsWith('image/')) return FileImage;
  if (mimeType.includes('presentation')) return Presentation;
  if (mimeType.includes('javascript') || mimeType.includes('typescript') || mimeType.includes('json')) return FileCode2;
  if (mimeType.includes('text') || mimeType.includes('markdown')) return FileText;
  return FileType;
}

function kindLabel(kind?: string | null): string {
  if (kind === 'document') return '文档';
  if (kind === 'ppt') return 'PPT';
  if (kind === 'image') return '图片';
  if (kind === 'archive') return '压缩包';
  if (kind === 'code') return '代码';
  if (kind === 'workflow') return 'Workflow';
  return '文件';
}

function metadataNumber(metadata: Record<string, unknown> | undefined, key: string): number | null {
  const value = metadata?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function metadataEntries(metadata: Record<string, unknown> | undefined): string[] {
  const value = metadata?.top_entries;
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

export function FileBlock({
  filename,
  path,
  url,
  size,
  mimeType,
  artifactKind = 'other',
  previewText,
  previewTruncated,
  metadata,
}: {
  filename: string;
  path?: string | null;
  url: string;
  size: number;
  mimeType: string;
  artifactKind?: string | null;
  previewText?: string | null;
  previewTruncated?: boolean | null;
  metadata?: Record<string, unknown>;
}) {
  const Icon = getFileIcon(mimeType);
  const [previewOpen, setPreviewOpen] = useState(false);
  const isImage = artifactKind === 'image' || mimeType.startsWith('image/');
  const canPreview = Boolean(previewText) || (isImage && Boolean(url));
  const slideCount = metadataNumber(metadata, 'slide_count');
  const fileCount = metadataNumber(metadata, 'file_count');
  const entries = metadataEntries(metadata);

  return (
    <>
      <div className="my-3 flex items-center gap-3 rounded-md border border-slate-700 bg-slate-950 p-3 text-sm transition hover:border-brand hover:bg-slate-900">
        {isImage && url ? (
          <button
            type="button"
            onClick={() => setPreviewOpen(true)}
            className="h-12 w-12 shrink-0 overflow-hidden rounded-md border border-slate-800 bg-slate-900"
            title="预览图片"
          >
            <img src={url} alt={filename} className="h-full w-full object-cover" />
          </button>
        ) : (
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-slate-900 text-brand-light">
            <Icon className="h-5 w-5" />
          </span>
        )}
        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate font-medium text-slate-100">{filename}</span>
            <span className="shrink-0 rounded border border-slate-700 px-1.5 py-0.5 text-[11px] text-slate-400">
              {kindLabel(artifactKind)}
            </span>
          </span>
          <span className="mt-1 block truncate text-xs text-slate-500">
            {mimeType} · {formatBytes(size)}
          </span>
          {path && path !== filename && (
            <span className="mt-1 block truncate text-xs text-slate-600 dark:text-slate-500">
              {path}
            </span>
          )}
          {(slideCount !== null || fileCount !== null) && (
            <span className="mt-1 block truncate text-xs text-slate-500">
              {slideCount !== null ? `${slideCount} slides` : null}
              {slideCount !== null && fileCount !== null ? ' · ' : null}
              {fileCount !== null ? `${fileCount} files` : null}
            </span>
          )}
          {entries.length > 0 && (
            <span className="mt-1 block truncate text-xs text-slate-500">
              {entries.slice(0, 4).join(', ')}
            </span>
          )}
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
          onClick={(event) => handleExternalLink(event, url)}
          target="_blank"
          rel="noreferrer"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-800 hover:text-white"
          title="打开外链"
        >
          <ExternalLink className="h-4 w-4" />
        </a>
      </div>

      {previewOpen && canPreview && (
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
              {isImage && url ? (
                <div className="flex min-h-56 items-center justify-center">
                  <img src={url} alt={filename} className="max-h-[70vh] max-w-full object-contain" />
                </div>
              ) : mimeType.includes('markdown') && previewText ? (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  className="prose prose-invert max-w-none prose-p:leading-7 prose-li:my-1 prose-code:text-brand-light"
                >
                  {previewText}
                </ReactMarkdown>
              ) : (
                <pre className="whitespace-pre-wrap text-sm leading-6 text-slate-200">
                  {previewText}
                  {previewTruncated ? '\n\n…' : ''}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
