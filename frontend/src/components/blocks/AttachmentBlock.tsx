import { Archive, Download, FileText, Image as ImageIcon, ShieldAlert } from 'lucide-react';
import { uploadDownloadUrl } from '@/lib/adapters/uploads';
import type { AttachmentBlock as AttachmentBlockData } from '@/lib/types';
import { cn } from '@/lib/utils';

const PREVIEW_LABELS: Record<NonNullable<AttachmentBlockData['preview']>['kind'], string> = {
  image: '图片',
  archive: '压缩包',
  document: '文档',
  text: '文本',
  code: '代码',
  unknown: '文件',
};

export function AttachmentBlock({ block }: { block: AttachmentBlockData }) {
  const preview = block.preview;
  const kind = preview?.kind ?? 'unknown';
  const Icon = kind === 'image' ? ImageIcon : kind === 'archive' ? Archive : FileText;
  const blocked = block.safety_status === 'blocked';
  const downloadUrl = preview?.url ?? uploadDownloadUrl(block.upload_id);

  return (
    <section className="mobile-text-safe my-3 overflow-hidden rounded-md border border-slate-300 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950/70">
      <div className="flex min-w-0 items-start gap-3 p-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-brand/25 bg-brand/10 text-brand dark:text-brand-light">
          <Icon className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h4 className="mobile-text-safe min-w-0 text-sm font-semibold text-slate-950 dark:text-white">
              {block.filename}
            </h4>
            <span className="shrink-0 rounded border border-slate-200 px-1.5 py-0.5 text-[11px] text-slate-500 dark:border-slate-800 dark:text-slate-400">
              {PREVIEW_LABELS[kind]}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {block.content_type} · {formatSize(block.size_bytes)}
          </p>
          {blocked && (
            <p className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-xs text-rose-700 dark:border-rose-400/25 dark:bg-rose-950/25 dark:text-rose-200">
              <ShieldAlert className="h-3.5 w-3.5" />
              安全检查未通过，已禁用下载和导入。
            </p>
          )}
          {preview?.text_preview && (
            <p className="mobile-text-safe mt-2 line-clamp-3 rounded-md bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              {preview.text_preview}
            </p>
          )}
          {kind === 'archive' && preview?.entries_preview?.length ? (
            <p className="mobile-text-safe mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
              包含：{preview.entries_preview.slice(0, 5).join(', ')}
            </p>
          ) : null}
          {kind === 'image' && (preview?.thumbnail_url || preview?.url) && (
            <img
              src={preview.thumbnail_url ?? preview.url}
              alt={block.filename}
              className="mt-3 max-h-56 max-w-full rounded-md border border-slate-200 object-contain dark:border-slate-800"
            />
          )}
        </div>
        <a
          href={blocked ? undefined : downloadUrl}
          target="_blank"
          rel="noreferrer"
          aria-disabled={blocked}
          className={cn(
            'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-slate-200 text-slate-500 transition hover:border-brand/40 hover:bg-brand/10 hover:text-brand dark:border-slate-800 dark:text-slate-400 dark:hover:text-brand-light',
            blocked && 'pointer-events-none opacity-40',
          )}
          title="下载附件"
        >
          <Download className="h-4 w-4" />
        </a>
      </div>
    </section>
  );
}

function formatSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
