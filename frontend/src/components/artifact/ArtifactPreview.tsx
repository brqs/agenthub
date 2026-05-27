import { Check, Code2, ExternalLink, FileText, Loader2, Monitor, PackageOpen, Save } from 'lucide-react';
import { useEffect, useState } from 'react';

export interface PreviewArtifactFile {
  path: string;
  name: string;
  mime_type: string;
  size: number;
  content: string | Blob;
}

function isTextMime(mimeType: string): boolean {
  return mimeType.startsWith('text/') || ['application/json', 'application/javascript'].includes(mimeType);
}

export function ArtifactPreview({
  artifact,
  isSaving = false,
  onSave,
}: {
  artifact: PreviewArtifactFile | null;
  isSaving?: boolean;
  onSave?: (path: string, content: string, mimeType: string) => Promise<void> | void;
}) {
  const [draft, setDraft] = useState('');
  const [saved, setSaved] = useState(false);
  const canEdit = Boolean(artifact && typeof artifact.content === 'string' && isTextMime(artifact.mime_type));
  const isDirty = canEdit && artifact !== null && draft !== artifact.content;

  useEffect(() => {
    setDraft(typeof artifact?.content === 'string' ? artifact.content : '');
    setSaved(false);
  }, [artifact?.path, artifact?.content]);

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
        {canEdit && onSave && (
          <button
            type="button"
            disabled={!isDirty || isSaving}
            onClick={async () => {
              await onSave(artifact.path, draft, artifact.mime_type);
              setSaved(true);
              window.setTimeout(() => setSaved(false), 1200);
            }}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-800 px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
          >
            {isSaving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : saved ? (
              <Check className="h-3.5 w-3.5 text-emerald-400" />
            ) : (
              <Save className="h-3.5 w-3.5" />
            )}
            {saved ? '已保存' : '保存'}
          </button>
        )}
        {isHtml && <ExternalLink className="h-4 w-4 shrink-0 text-slate-600" />}
      </div>

      {isHtml && typeof artifact.content === 'string' ? (
        <div className="grid min-h-72 grid-rows-[minmax(12rem,1fr)_minmax(10rem,0.8fr)]">
          <iframe
            title={artifact.name}
            srcDoc={draft}
            sandbox=""
            className="h-full min-h-48 w-full border-0 bg-white"
          />
          <textarea
            aria-label={`${artifact.name} source`}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            spellCheck={false}
            className="min-h-40 w-full resize-y border-t border-slate-800 bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-300 outline-none scrollbar-thin"
          />
        </div>
      ) : isTextMime(artifact.mime_type) && typeof artifact.content === 'string' ? (
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          spellCheck={false}
          className="min-h-56 w-full resize-y bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-300 outline-none scrollbar-thin"
        />
      ) : (
        <div className="flex flex-col items-center justify-center gap-2 p-6 text-center text-sm text-slate-500">
          <PackageOpen className="h-6 w-6 text-slate-600" />
          当前仅支持预览 HTML 与文本文件。
        </div>
      )}
    </section>
  );
}
