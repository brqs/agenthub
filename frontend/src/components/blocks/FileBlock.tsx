import { ExternalLink, FileArchive, FileCode2, FileText, FileType } from 'lucide-react';

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
}: {
  filename: string;
  url: string;
  size: number;
  mimeType: string;
}) {
  const Icon = getFileIcon(mimeType);

  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="my-3 flex items-center gap-3 rounded-md border border-slate-700 bg-slate-950 p-3 text-sm transition hover:border-brand hover:bg-slate-900"
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-slate-900 text-brand-light">
        <Icon className="h-5 w-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-slate-100">{filename}</span>
        <span className="mt-1 block truncate text-xs text-slate-500">
          {mimeType} · {formatBytes(size)}
        </span>
      </span>
      <ExternalLink className="h-4 w-4 shrink-0 text-slate-500" />
    </a>
  );
}
