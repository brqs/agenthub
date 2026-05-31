import {
  Check,
  Code2,
  Edit3,
  FileText,
  Image,
  Loader2,
  Maximize2,
  Monitor,
  PackageOpen,
  Save,
  Upload,
  X,
} from 'lucide-react';
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

function canEmbedBlob(mimeType: string): boolean {
  return mimeType.startsWith('image/') || mimeType.startsWith('video/') || mimeType.startsWith('audio/') || mimeType === 'application/pdf';
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  return `${(size / 1024).toFixed(1)} KB`;
}

export function ArtifactPreview({
  artifact,
  isSaving = false,
  onSave,
}: {
  artifact: PreviewArtifactFile | null;
  isSaving?: boolean;
  onSave?: (path: string, content: string | Blob, mimeType: string) => Promise<void> | void;
}) {
  const [draft, setDraft] = useState('');
  const [replacement, setReplacement] = useState<File | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [saved, setSaved] = useState(false);
  const blobContent = replacement ?? (artifact?.content instanceof Blob ? artifact.content : null);
  const blobUrl = useBlobUrl(blobContent);
  const canEditText = Boolean(artifact && typeof artifact.content === 'string' && isTextMime(artifact.mime_type));
  const isDirty = Boolean(artifact && (replacement || (canEditText && draft !== artifact.content)));

  useEffect(() => {
    setDraft(typeof artifact?.content === 'string' ? artifact.content : '');
    setReplacement(null);
    setIsEditing(false);
    setSaved(false);
  }, [artifact?.path, artifact?.content]);

  useEffect(() => {
    if (!isFullscreen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setIsFullscreen(false);
    }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [isFullscreen]);

  if (!artifact) {
    return (
      <div className="rounded-md border border-dashed border-slate-800 p-4 text-sm text-slate-500">
        选择一个 workspace 文件查看预览
      </div>
    );
  }

  async function save() {
    if (!artifact || !onSave || !isDirty) return;
    await onSave(
      artifact.path,
      replacement ?? draft,
      replacement?.type || artifact.mime_type,
    );
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1200);
  }

  const content = (
    <ArtifactContent
      artifact={artifact}
      blobUrl={blobUrl}
      draft={draft}
      isEditing={isEditing}
      onDraftChange={setDraft}
      onReplacementChange={setReplacement}
    />
  );

  return (
    <>
      <section className="overflow-hidden rounded-md border border-slate-800 bg-slate-950/60">
        <ArtifactHeader
          artifact={artifact}
          isEditing={isEditing}
          isDirty={isDirty}
          isSaving={isSaving}
          saved={saved}
          onEdit={() => setIsEditing((value) => !value)}
          onFullscreen={() => setIsFullscreen(true)}
          onSave={save}
          canSave={Boolean(onSave)}
        />
        {!isFullscreen && content}
      </section>

      {isFullscreen && (
        <div className="fixed inset-0 z-[70] flex bg-slate-950/90 p-4 backdrop-blur-sm">
          <section className="flex min-h-0 w-full flex-col overflow-hidden rounded-md border border-slate-700 bg-slate-900 shadow-2xl shadow-black/50">
            <ArtifactHeader
              artifact={artifact}
              isEditing={isEditing}
              isDirty={isDirty}
              isSaving={isSaving}
              saved={saved}
              onEdit={() => setIsEditing((value) => !value)}
              onFullscreen={() => setIsFullscreen(false)}
              onSave={save}
              canSave={Boolean(onSave)}
              isFullscreen
            />
            <div className="min-h-0 flex-1 overflow-auto">{content}</div>
          </section>
        </div>
      )}
    </>
  );
}

function ArtifactHeader({
  artifact,
  isEditing,
  isDirty,
  isSaving,
  saved,
  onEdit,
  onFullscreen,
  onSave,
  canSave,
  isFullscreen = false,
}: {
  artifact: PreviewArtifactFile;
  isEditing: boolean;
  isDirty: boolean;
  isSaving: boolean;
  saved: boolean;
  onEdit: () => void;
  onFullscreen: () => void;
  onSave: () => void;
  canSave: boolean;
  isFullscreen?: boolean;
}) {
  const Icon = artifact.mime_type === 'text/html' ? Monitor : isTextMime(artifact.mime_type) ? Code2 : FileText;

  return (
    <div className="flex min-w-0 items-center gap-2 border-b border-slate-800 px-3 py-2">
      <Icon className="h-4 w-4 shrink-0 text-brand-light" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-white">{artifact.name}</div>
        <div className="truncate text-xs text-slate-500">{artifact.mime_type} · {formatSize(artifact.size)}</div>
      </div>
      {canSave && (
        <button
          type="button"
          onClick={onEdit}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-800 px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-white"
          aria-label={isEditing ? '退出修改模式' : '修改模式'}
        >
          <Edit3 className="h-3.5 w-3.5" />
          {isEditing ? '退出修改' : '修改'}
        </button>
      )}
      {isEditing && canSave && (
        <button
          type="button"
          disabled={!isDirty || isSaving}
          onClick={() => void onSave()}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-800 px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
        >
          {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : saved ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Save className="h-3.5 w-3.5" />}
          {saved ? '已保存' : '保存'}
        </button>
      )}
      <button
        type="button"
        onClick={onFullscreen}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-800 px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-white"
        aria-label={isFullscreen ? '退出全屏预览' : '全屏预览'}
      >
        {isFullscreen ? <X className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
        {isFullscreen ? '关闭' : '全屏'}
      </button>
    </div>
  );
}

function ArtifactContent({
  artifact,
  blobUrl,
  draft,
  isEditing,
  onDraftChange,
  onReplacementChange,
}: {
  artifact: PreviewArtifactFile;
  blobUrl: string | null;
  draft: string;
  isEditing: boolean;
  onDraftChange: (value: string) => void;
  onReplacementChange: (file: File | null) => void;
}) {
  if (isEditing) {
    if (typeof artifact.content === 'string' && isTextMime(artifact.mime_type)) {
      return (
        <textarea
          aria-label={`${artifact.name} source`}
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          spellCheck={false}
          className="min-h-72 w-full resize-y bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-300 outline-none scrollbar-thin"
        />
      );
    }
    return (
      <label className="flex min-h-56 cursor-pointer flex-col items-center justify-center gap-3 p-6 text-center text-sm text-slate-400">
        <Upload className="h-7 w-7 text-brand-light" />
        <span>选择新文件替换当前 workspace 文件</span>
        <input
          type="file"
          className="max-w-full text-xs"
          aria-label={`替换 ${artifact.name}`}
          onChange={(event) => onReplacementChange(event.target.files?.[0] ?? null)}
        />
      </label>
    );
  }

  if (artifact.mime_type === 'text/html' && typeof artifact.content === 'string') {
    return <iframe title={artifact.name} srcDoc={draft} sandbox="" className="h-[32rem] w-full border-0 bg-white" />;
  }
  if (typeof artifact.content === 'string' && isTextMime(artifact.mime_type)) {
    return <pre className="max-h-[36rem] overflow-auto whitespace-pre-wrap p-3 font-mono text-xs leading-5 text-slate-300 scrollbar-thin">{draft}</pre>;
  }
  if (blobUrl && artifact.mime_type.startsWith('image/')) {
    return <div className="flex min-h-56 items-center justify-center bg-slate-950 p-3"><img src={blobUrl} alt={artifact.name} className="max-h-[70vh] max-w-full object-contain" /></div>;
  }
  if (blobUrl && artifact.mime_type.startsWith('video/')) {
    return <video src={blobUrl} controls className="max-h-[70vh] w-full bg-black" />;
  }
  if (blobUrl && artifact.mime_type.startsWith('audio/')) {
    return <div className="p-6"><audio src={blobUrl} controls className="w-full" /></div>;
  }
  if (blobUrl && artifact.mime_type === 'application/pdf') {
    return <iframe title={artifact.name} src={blobUrl} className="h-[70vh] w-full border-0 bg-white" />;
  }
  return (
    <div className="flex min-h-56 flex-col items-center justify-center gap-2 p-6 text-center text-sm text-slate-500">
      {canEmbedBlob(artifact.mime_type) ? <Image className="h-6 w-6 text-slate-600" /> : <PackageOpen className="h-6 w-6 text-slate-600" />}
      当前文件无法在浏览器中直接预览，可进入修改模式替换文件。
    </div>
  );
}

function useBlobUrl(blob: Blob | null): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!blob || typeof URL.createObjectURL !== 'function') {
      setUrl(null);
      return;
    }
    const nextUrl = URL.createObjectURL(blob);
    setUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [blob]);

  return url;
}
