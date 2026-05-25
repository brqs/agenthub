import { ExternalLink, Globe2, Maximize2, X } from 'lucide-react';
import { useState } from 'react';

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
  previewTitle,
  previewBody,
}: {
  url: string;
  title?: string | null;
  description?: string | null;
  previewTitle?: string | null;
  previewBody?: string | null;
}) {
  const [previewOpen, setPreviewOpen] = useState(false);

  return (
    <>
      <div className="my-3 overflow-hidden rounded-md border border-slate-700 bg-slate-950 transition hover:border-brand hover:bg-slate-900">
        <div className="border-b border-slate-800 bg-slate-900/70 px-4 py-3">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Globe2 className="h-3.5 w-3.5" />
            <span className="truncate">{getHostname(url)}</span>
            <button
              type="button"
              onClick={() => setPreviewOpen(true)}
              className="ml-auto rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-white"
              title="预览网页"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-white"
              title="打开外链"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
        <button type="button" onClick={() => setPreviewOpen(true)} className="block w-full px-4 py-3 text-left">
          <div className="line-clamp-2 text-sm font-medium text-slate-100">{title ?? url}</div>
          {description && (
            <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-500">{description}</p>
          )}
          <div className="mt-3 truncate text-xs text-brand-light">{url}</div>
        </button>
      </div>

      {previewOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 backdrop-blur-sm">
          <div className="flex max-h-[84vh] w-full max-w-5xl flex-col overflow-hidden rounded-md border border-slate-700 bg-slate-900 shadow-2xl shadow-black/40">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-white">{title ?? url}</div>
                <div className="mt-1 truncate text-xs text-slate-500">{url}</div>
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
            <div className="min-h-0 overflow-y-auto bg-slate-950 p-4 scrollbar-thin">
              <div className="overflow-hidden rounded-md border border-slate-800 bg-slate-900">
                <div className="flex items-center gap-2 border-b border-slate-800 bg-slate-950 px-3 py-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
                  <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                  <span className="ml-3 min-w-0 flex-1 truncate rounded bg-slate-900 px-3 py-1 text-xs text-slate-500">
                    {url}
                  </span>
                </div>
                <div className="bg-slate-100 p-6 text-slate-950">
                  <div className="mx-auto max-w-3xl">
                    <div className="text-xs font-semibold uppercase tracking-wide text-cyan-700">AgentHub Preview</div>
                    <h3 className="mt-3 text-3xl font-bold tracking-normal text-slate-950">
                      {previewTitle ?? title ?? '构建预览'}
                    </h3>
                    <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
                      {previewBody ?? description ?? '该网页预览来自 Agent 产物，当前 Demo 使用 Mock 页面模拟真实构建结果。'}
                    </p>
                    <div className="mt-6 grid gap-3 sm:grid-cols-3">
                      {['Chat Shell', 'Agent Flow', 'Rich Blocks'].map((item) => (
                        <div key={item} className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
                          <div className="text-sm font-semibold text-slate-900">{item}</div>
                          <div className="mt-2 h-2 rounded bg-cyan-100" />
                          <div className="mt-2 h-2 w-2/3 rounded bg-slate-100" />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
