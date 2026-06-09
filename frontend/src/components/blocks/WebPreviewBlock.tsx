import { ExternalLink, Globe2, Maximize2, X } from 'lucide-react';
import { useState } from 'react';
import { handleExternalLink } from '@/lib/nativeShell';

const PREVIEW_IFRAME_SANDBOX =
  'allow-scripts allow-same-origin allow-forms allow-popups allow-downloads';

function getHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function isPreviewUrlAllowed(url: string): boolean {
  try {
    const protocol = new URL(url).protocol;
    return protocol === 'http:' || protocol === 'https:';
  } catch {
    return false;
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
  const [iframeLoaded, setIframeLoaded] = useState(false);
  const [iframeErrored, setIframeErrored] = useState(false);
  const previewAllowed = isPreviewUrlAllowed(url);
  const displayTitle = title ?? previewTitle ?? url;
  const displayDescription = description ?? previewBody;

  function openPreview() {
    setIframeLoaded(false);
    setIframeErrored(false);
    setPreviewOpen(true);
  }

  return (
    <>
      <div className="my-3 overflow-hidden rounded-md border border-slate-300 bg-white transition hover:border-brand hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:hover:bg-slate-900">
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/70">
          <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-500">
            <Globe2 className="h-3.5 w-3.5" />
            <span className="truncate">{getHostname(url)}</span>
            <button
              type="button"
              onClick={openPreview}
              className="ml-auto rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
              title="预览网页"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
            {previewAllowed && (
              <a
                href={url}
                onClick={(event) => handleExternalLink(event, url)}
                target="_blank"
                rel="noreferrer"
                className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
                title="打开外链"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
        </div>
        <button type="button" onClick={openPreview} className="block w-full px-4 py-3 text-left">
          <div className="line-clamp-2 text-sm font-medium text-slate-950 dark:text-slate-100">
            {displayTitle}
          </div>
          {displayDescription && (
            <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-600 dark:text-slate-500">
              {displayDescription}
            </p>
          )}
          <div className="mt-3 truncate text-xs text-brand dark:text-brand-light">{url}</div>
        </button>
      </div>

      {previewOpen && (
        <div className="fixed inset-0 z-50 flex h-[100dvh] items-center justify-center bg-slate-950/80 backdrop-blur-sm sm:px-4 sm:py-6">
          <div className="flex h-full w-full flex-col overflow-hidden border border-slate-300 bg-white shadow-2xl shadow-black/20 dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/40 sm:max-h-[86vh] sm:max-w-[min(1280px,calc(100vw-2rem))] sm:rounded-md">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-slate-950 dark:text-white">
                  {displayTitle}
                </div>
                <div className="mt-1 truncate text-xs text-slate-600 dark:text-slate-500">
                  {url}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {previewAllowed && (
                  <a
                    href={url}
                    onClick={(event) => handleExternalLink(event, url)}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
                    title="新窗口打开"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => setPreviewOpen(false)}
                  className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white"
                  title="关闭预览"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 bg-slate-950 p-2 sm:p-4">
              <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-md border border-slate-800 bg-slate-900">
                <div className="flex items-center gap-2 border-b border-slate-800 bg-slate-950 px-3 py-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
                  <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                  <span className="ml-3 min-w-0 flex-1 truncate rounded bg-slate-900 px-3 py-1 text-xs text-slate-500">
                    {url}
                  </span>
                </div>
                <div className="group relative min-h-0 flex-1 bg-white">
                  {!previewAllowed ? (
                    <div className="flex h-full items-center justify-center p-6 text-center text-sm leading-6 text-slate-600">
                      预览 URL 不合法，无法嵌入展示。
                    </div>
                  ) : (
                    <>
                      {!iframeLoaded && !iframeErrored && (
                        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-white/90 text-sm text-slate-500">
                          正在加载真实预览…
                        </div>
                      )}
                      {iframeErrored && (
                        <div className="absolute inset-x-4 top-4 z-20 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 shadow-sm">
                          预览嵌入加载失败，请尝试新窗口打开。
                        </div>
                      )}
                      <iframe
                        title={displayTitle}
                        src={url}
                        className="h-full w-full border-0 bg-white"
                        sandbox={PREVIEW_IFRAME_SANDBOX}
                        referrerPolicy="no-referrer"
                        onLoad={() => setIframeLoaded(true)}
                        onError={() => setIframeErrored(true)}
                      />
                      <div className="pointer-events-none absolute bottom-3 left-3 right-3 rounded-md bg-slate-950/75 px-3 py-2 text-xs leading-5 text-slate-200 opacity-0 transition group-hover:opacity-100">
                        如果预览区域为空白，可能是浏览器阻止了嵌入预览。请点击“新窗口打开”查看真实页面。
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
