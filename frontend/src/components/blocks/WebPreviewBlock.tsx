import { ExternalLink, Globe2 } from 'lucide-react';

function getHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export function WebPreviewBlock({
  url,
  title,
  description,
}: {
  url: string;
  title?: string | null;
  description?: string | null;
}) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="my-3 block overflow-hidden rounded-md border border-slate-700 bg-slate-950 transition hover:border-brand hover:bg-slate-900"
    >
      <div className="border-b border-slate-800 bg-slate-900/70 px-4 py-3">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Globe2 className="h-3.5 w-3.5" />
          <span className="truncate">{getHostname(url)}</span>
          <ExternalLink className="ml-auto h-3.5 w-3.5" />
        </div>
      </div>
      <div className="px-4 py-3">
        <div className="line-clamp-2 text-sm font-medium text-slate-100">{title ?? url}</div>
        {description && (
          <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-500">{description}</p>
        )}
        <div className="mt-3 truncate text-xs text-brand-light">{url}</div>
      </div>
    </a>
  );
}
