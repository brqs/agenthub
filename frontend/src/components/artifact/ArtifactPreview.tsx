import { Code2, ExternalLink, FileText, Monitor, PackageOpen } from 'lucide-react';
import type { MockArtifactFile } from '@/lib/mockWorkspace';

function isTextMime(mimeType: string): boolean {
  return mimeType.startsWith('text/') || ['application/json', 'application/javascript'].includes(mimeType);
}

export function ArtifactPreview({ artifact }: { artifact: MockArtifactFile | null }) {
  if (!artifact) {
    return (
      <div className="rounded-md border border-dashed border-slate-800 p-4 text-sm text-slate-500">
        选择一个 workspace 文件查看预览
      </div>
    );
  }

  const isHtml = artifact.mime_type === 'text/html';

  return (
    <section className="overflow-hidden rounded-md border border-slate-800 bg-slate-950/60">
      <div className="flex min-w-0 items-center gap-2 border-b border-slate-800 px-3 py-2">
        {isHtml ? (
          <Monitor className="h-4 w-4 shrink-0 text-brand-light" />
        ) : isTextMime(artifact.mime_type) ? (
          <Code2 className="h-4 w-4 shrink-0 text-brand-light" />
        ) : (
          <FileText className="h-4 w-4 shrink-0 text-brand-light" />
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-white">{artifact.name}</div>
          <div className="truncate text-xs text-slate-500">{artifact.mime_type}</div>
        </div>
        {isHtml && <ExternalLink className="h-4 w-4 shrink-0 text-slate-600" />}
      </div>

      {isHtml ? (
        <iframe
          title={artifact.name}
          srcDoc={artifact.content}
          sandbox=""
          className="h-64 w-full border-0 bg-white"
        />
      ) : isTextMime(artifact.mime_type) ? (
        <pre className="max-h-72 overflow-auto p-3 text-xs leading-5 text-slate-300 scrollbar-thin">
          {artifact.content}
        </pre>
      ) : (
        <div className="flex flex-col items-center justify-center gap-2 p-6 text-center text-sm text-slate-500">
          <PackageOpen className="h-6 w-6 text-slate-600" />
          当前 Mock 预览只展示 HTML 与文本文件。
        </div>
      )}
    </section>
  );
}
