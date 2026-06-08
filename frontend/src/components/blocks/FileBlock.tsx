import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
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
import type { ArtifactEvaluationStatus } from '@/lib/adapters/workspaces';

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(mimeType: string) {
  if (mimeType.includes('zip') || mimeType.includes('tar')) return FileArchive;
  if (mimeType.startsWith('image/')) return FileImage;
  if (mimeType.includes('presentation')) return Presentation;
  if (
    mimeType.includes('javascript') ||
    mimeType.includes('typescript') ||
    mimeType.includes('json')
  )
    return FileCode2;
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

function evaluationPresentation(status: ArtifactEvaluationStatus) {
  if (status === 'passed') {
    return {
      icon: CheckCircle2,
      label: '评估通过',
      className:
        'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200',
    };
  }
  if (status === 'failed') {
    return {
      icon: AlertTriangle,
      label: '评估失败',
      className:
        'border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200',
    };
  }
  if (status === 'manual_review_required') {
    return {
      icon: CircleHelp,
      label: '需人工复核',
      className:
        'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200',
    };
  }
  return {
    icon: CircleHelp,
    label: '评估未知',
    className:
      'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400',
  };
}

function metadataNumber(metadata: Record<string, unknown> | undefined, key: string): number | null {
  const value = metadata?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function metadataEntries(metadata: Record<string, unknown> | undefined): string[] {
  const value = metadata?.top_entries;
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function metadataStringList(metadata: Record<string, unknown> | undefined, key: string): string[] {
  const value = metadata?.[key];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function evaluationSummary(results: Array<Record<string, unknown>> | undefined): string | null {
  const first = results?.[0];
  if (!first) return null;
  const issues = first.issues;
  if (Array.isArray(issues) && issues.length > 0) {
    return issues
      .slice(0, 2)
      .map((issue) => (typeof issue === 'string' ? issue : JSON.stringify(issue)))
      .join('；');
  }
  const message = first.message ?? first.summary ?? first.error;
  return typeof message === 'string' && message.trim() ? message : null;
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
  evaluationStatus = 'unknown',
  evaluationResults,
  taskId,
  runId,
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
  evaluationStatus?: ArtifactEvaluationStatus;
  evaluationResults?: Array<Record<string, unknown>>;
  taskId?: string | null;
  runId?: string | null;
}) {
  const Icon = getFileIcon(mimeType);
  const [previewOpen, setPreviewOpen] = useState(false);
  const isImage = artifactKind === 'image' || mimeType.startsWith('image/');
  const slideCount = metadataNumber(metadata, 'slide_count');
  const pageCount = metadataNumber(metadata, 'page_count');
  const wordCount = metadataNumber(metadata, 'word_count');
  const fileCount = metadataNumber(metadata, 'file_count');
  const totalSize = metadataNumber(metadata, 'total_size');
  const entries = metadataEntries(metadata);
  const headings = metadataStringList(metadata, 'headings');
  const slideTitles = metadataStringList(metadata, 'slide_titles');
  const hasRichMetadata = Boolean(
    pageCount !== null ||
    wordCount !== null ||
    headings.length ||
    slideTitles.length ||
    entries.length,
  );
  const canPreview = Boolean(previewText || hasRichMetadata) || (isImage && Boolean(url));
  const evaluation = evaluationPresentation(evaluationStatus);
  const EvaluationIcon = evaluation.icon;
  const evalSummary = evaluationSummary(evaluationResults);

  return (
    <>
      <div className="mobile-text-safe my-3 flex items-start gap-3 rounded-md border border-slate-300 bg-white p-3 text-sm shadow-sm transition hover:border-brand hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:hover:bg-slate-900">
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
        <span className="min-w-0 max-w-full flex-1">
          <span className="flex min-w-0 items-center gap-2">
            <span className="mobile-text-safe font-medium text-slate-100 sm:truncate">
              {filename}
            </span>
            <span className="shrink-0 rounded border border-slate-700 px-1.5 py-0.5 text-[11px] text-slate-400">
              {kindLabel(artifactKind)}
            </span>
          </span>
          <span className="mobile-text-safe mt-1 block text-xs text-slate-500 sm:truncate">
            {mimeType} · {formatBytes(size)}
          </span>
          {path && path !== filename && (
            <span className="mobile-text-safe mt-1 block text-xs text-slate-600 dark:text-slate-500 sm:truncate">
              {path}
            </span>
          )}
          {(slideCount !== null ||
            pageCount !== null ||
            wordCount !== null ||
            fileCount !== null) && (
            <span className="mobile-text-safe mt-1 block text-xs text-slate-500 sm:truncate">
              {slideCount !== null ? `${slideCount} 页幻灯片` : null}
              {pageCount !== null ? `${slideCount !== null ? ' · ' : ''}${pageCount} 页文档` : null}
              {wordCount !== null
                ? `${slideCount !== null || pageCount !== null ? ' · ' : ''}${wordCount} 字`
                : null}
              {(slideCount !== null || pageCount !== null || wordCount !== null) &&
              fileCount !== null
                ? ' · '
                : null}
              {fileCount !== null ? `${fileCount} 个文件` : null}
              {fileCount !== null && totalSize !== null ? ` · ${formatBytes(totalSize)}` : null}
            </span>
          )}
          {entries.length > 0 && (
            <span className="mobile-text-safe mt-1 block text-xs text-slate-500 sm:truncate">
              {entries.slice(0, 4).join(', ')}
            </span>
          )}
          <span className="mt-2 flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${evaluation.className}`}
            >
              <EvaluationIcon className="h-3 w-3" />
              {evaluation.label}
            </span>
            {taskId && (
              <span className="mobile-text-safe max-w-40 rounded-full border border-slate-200 px-2 py-0.5 text-[11px] text-slate-500 dark:border-slate-800 sm:truncate">
                task {taskId}
              </span>
            )}
            {runId && (
              <span className="mobile-text-safe max-w-40 rounded-full border border-slate-200 px-2 py-0.5 text-[11px] text-slate-500 dark:border-slate-800 sm:truncate">
                run {runId}
              </span>
            )}
          </span>
          {evalSummary && (
            <span className="mobile-text-safe mt-1 block line-clamp-2 text-xs leading-5 text-slate-600 dark:text-slate-400">
              {evalSummary}
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
              <div className="mobile-text-safe">
                <div className="mobile-text-safe text-sm font-semibold text-white sm:truncate">
                  {filename}
                </div>
                <div className="mobile-text-safe mt-1 text-xs text-slate-500">
                  {mimeType} · {formatBytes(size)}
                </div>
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
            <div className="mobile-text-safe min-h-0 overflow-y-auto bg-slate-950 p-4 scrollbar-thin sm:p-6">
              {isImage && url ? (
                <div className="flex min-h-56 items-center justify-center">
                  <img
                    src={url}
                    alt={filename}
                    className="max-h-[70vh] max-w-full object-contain"
                  />
                </div>
              ) : mimeType.includes('markdown') && previewText ? (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  className="prose prose-invert chat-markdown-safe max-w-none prose-p:leading-7 prose-li:my-1 prose-code:text-brand-light"
                >
                  {previewText}
                </ReactMarkdown>
              ) : hasRichMetadata ? (
                <div className="space-y-4 text-sm leading-6 text-slate-200">
                  {(pageCount !== null ||
                    wordCount !== null ||
                    slideCount !== null ||
                    fileCount !== null) && (
                    <div className="grid gap-2 sm:grid-cols-3">
                      {pageCount !== null && (
                        <RichPreviewStat label="页数" value={`${pageCount}`} />
                      )}
                      {wordCount !== null && (
                        <RichPreviewStat label="字数" value={`${wordCount}`} />
                      )}
                      {slideCount !== null && (
                        <RichPreviewStat label="幻灯片" value={`${slideCount}`} />
                      )}
                      {fileCount !== null && (
                        <RichPreviewStat label="文件数" value={`${fileCount}`} />
                      )}
                    </div>
                  )}
                  {headings.length > 0 && <RichPreviewList title="文档标题" items={headings} />}
                  {slideTitles.length > 0 && (
                    <RichPreviewList title="幻灯片标题" items={slideTitles} />
                  )}
                  {entries.length > 0 && <RichPreviewList title="压缩包内容" items={entries} />}
                  {previewText && (
                    <pre className="mobile-text-safe whitespace-pre-wrap text-sm leading-6 text-slate-200">
                      {previewText}
                      {previewTruncated ? '\n\n…' : ''}
                    </pre>
                  )}
                </div>
              ) : (
                <pre className="mobile-text-safe whitespace-pre-wrap text-sm leading-6 text-slate-200">
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

function RichPreviewStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900 px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 font-medium text-slate-100">{value}</div>
    </div>
  );
}

function RichPreviewList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </div>
      <ul className="space-y-1">
        {items.slice(0, 12).map((item) => (
          <li key={item} className="mobile-text-safe rounded bg-slate-900 px-3 py-2 text-slate-200">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
