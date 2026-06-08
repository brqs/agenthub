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
import { WorkspaceCodePreview } from './WorkspaceCodePreview';
import type { ArtifactEvaluationStatus, WorkspaceArtifact } from '@/lib/adapters/workspaces';
import { cn } from '@/lib/utils';

export interface PreviewArtifactFile {
  path: string;
  name: string;
  mime_type: string;
  size: number;
  content: string | Blob;
  artifact_kind?: WorkspaceArtifact['artifact_kind'];
  preview_text?: string | null;
  preview_truncated?: boolean | null;
  metadata?: Record<string, unknown>;
  evaluation_status?: ArtifactEvaluationStatus;
  evaluation_results?: Array<Record<string, unknown>>;
  task_id?: string | null;
  run_id?: string | null;
}

function isTextMime(mimeType: string): boolean {
  return (
    mimeType.startsWith('text/') ||
    ['application/json', 'application/javascript'].includes(mimeType)
  );
}

function canEmbedBlob(mimeType: string): boolean {
  return (
    mimeType.startsWith('image/') ||
    mimeType.startsWith('video/') ||
    mimeType.startsWith('audio/') ||
    mimeType === 'application/pdf'
  );
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
  const canEditText = Boolean(
    artifact && typeof artifact.content === 'string' && isTextMime(artifact.mime_type),
  );
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
      <div className="rounded-md border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-slate-800">
        选择一个 workspace 文件查看预览
      </div>
    );
  }

  async function save() {
    if (!artifact || !onSave || !isDirty) return;
    await onSave(artifact.path, replacement ?? draft, replacement?.type || artifact.mime_type);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1200);
  }

  const content = (
    <ArtifactContent
      artifact={artifact}
      blobUrl={blobUrl}
      draft={draft}
      isEditing={isEditing}
      isFullscreen={isFullscreen}
      onDraftChange={setDraft}
      onReplacementChange={setReplacement}
    />
  );

  return (
    <>
      <section className="overflow-hidden rounded-md border border-slate-300 bg-white dark:border-slate-800 dark:bg-slate-950/60">
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
        <ArtifactInsight artifact={artifact} />
        {!isFullscreen && content}
      </section>

      {isFullscreen && (
        <div className="fixed inset-0 z-[70] flex h-[100dvh] bg-slate-950/60 backdrop-blur-sm dark:bg-slate-950/90 sm:p-4">
          <section className="flex min-h-0 w-full flex-col overflow-hidden border border-slate-300 bg-white shadow-2xl shadow-black/25 dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/50 sm:rounded-md">
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
            <ArtifactInsight artifact={artifact} />
            <div className="min-h-0 flex-1 overflow-auto">{content}</div>
          </section>
        </div>
      )}
    </>
  );
}

function ArtifactInsight({ artifact }: { artifact: PreviewArtifactFile }) {
  const kind = artifact.artifact_kind;
  if (!kind || kind === 'code' || kind === 'workflow' || kind === 'other') return null;
  const slideCount = metadataNumber(artifact.metadata, 'slide_count');
  const fileCount = metadataNumber(artifact.metadata, 'file_count');
  const entries = metadataStringList(artifact.metadata, 'top_entries');
  const status = artifact.evaluation_status ?? 'unknown';

  return (
    <div className="border-b border-slate-200 bg-slate-50 px-3 py-3 text-xs leading-5 dark:border-slate-800 dark:bg-slate-950/80">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-slate-300 px-2 py-0.5 font-medium text-slate-700 dark:border-slate-700 dark:text-slate-200">
          {artifactKindLabel(kind)}
        </span>
        <span className={cn('rounded-full border px-2 py-0.5', evaluationClassName(status))}>
          {evaluationLabel(status)}
        </span>
        {slideCount !== null && <span className="text-slate-500">{slideCount} 页幻灯片</span>}
        {fileCount !== null && <span className="text-slate-500">{fileCount} 个文件</span>}
        {artifact.task_id && (
          <span className="truncate text-slate-500">task {artifact.task_id}</span>
        )}
      </div>
      {artifact.preview_text && (
        <p className="mt-2 line-clamp-3 text-slate-600 dark:text-slate-400">
          {artifact.preview_text}
          {artifact.preview_truncated ? '…' : ''}
        </p>
      )}
      {entries.length > 0 && (
        <p className="mt-2 truncate text-slate-500">压缩包内容：{entries.slice(0, 6).join(', ')}</p>
      )}
    </div>
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
  const Icon =
    artifact.mime_type === 'text/html'
      ? Monitor
      : isTextMime(artifact.mime_type)
        ? Code2
        : FileText;

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 border-b border-slate-200 px-3 py-2 dark:border-slate-800">
      <Icon className="h-4 w-4 shrink-0 text-brand-light" />
      <div className="min-w-32 flex-1">
        <div className="truncate text-sm font-medium text-slate-950 dark:text-white">
          {artifact.name}
        </div>
        <div className="truncate text-xs text-slate-500">
          {artifact.mime_type} · {formatSize(artifact.size)}
        </div>
      </div>
      {canSave && (
        <button
          type="button"
          onClick={onEdit}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
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
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-45 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
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
      <button
        type="button"
        onClick={onFullscreen}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
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
  isFullscreen,
  onDraftChange,
  onReplacementChange,
}: {
  artifact: PreviewArtifactFile;
  blobUrl: string | null;
  draft: string;
  isEditing: boolean;
  isFullscreen: boolean;
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
          className="min-h-72 w-full resize-y bg-white p-3 font-mono text-xs leading-5 text-slate-900 outline-none scrollbar-thin dark:bg-slate-950 dark:text-slate-300"
        />
      );
    }
    return (
      <label className="flex min-h-56 cursor-pointer flex-col items-center justify-center gap-3 p-6 text-center text-sm text-slate-600 dark:text-slate-400">
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

  if (typeof artifact.content === 'string' && isTextMime(artifact.mime_type)) {
    return (
      <WorkspaceCodePreview
        filename={artifact.name}
        mimeType={artifact.mime_type}
        code={draft}
        isFullscreen={isFullscreen}
      />
    );
  }
  if (blobUrl && artifact.mime_type.startsWith('image/')) {
    return (
      <div className="flex min-h-56 items-center justify-center bg-slate-100 p-3 dark:bg-slate-950">
        <img src={blobUrl} alt={artifact.name} className="max-h-[70vh] max-w-full object-contain" />
      </div>
    );
  }
  if (blobUrl && artifact.mime_type.startsWith('video/')) {
    return <video src={blobUrl} controls className="max-h-[70vh] w-full bg-black" />;
  }
  if (blobUrl && artifact.mime_type.startsWith('audio/')) {
    return (
      <div className="p-6">
        <audio src={blobUrl} controls className="w-full" />
      </div>
    );
  }
  if (blobUrl && artifact.mime_type === 'application/pdf') {
    return (
      <iframe title={artifact.name} src={blobUrl} className="h-[70vh] w-full border-0 bg-white" />
    );
  }
  return (
    <div className="flex min-h-56 flex-col items-center justify-center gap-2 p-6 text-center text-sm text-slate-500">
      {canEmbedBlob(artifact.mime_type) ? (
        <Image className="h-6 w-6 text-slate-600" />
      ) : (
        <PackageOpen className="h-6 w-6 text-slate-600" />
      )}
      当前文件无法在浏览器中直接预览，可进入修改模式替换文件。
    </div>
  );
}

function metadataNumber(metadata: Record<string, unknown> | undefined, key: string): number | null {
  const value = metadata?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function metadataStringList(metadata: Record<string, unknown> | undefined, key: string): string[] {
  const value = metadata?.[key];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function artifactKindLabel(kind: WorkspaceArtifact['artifact_kind']) {
  const labels: Record<WorkspaceArtifact['artifact_kind'], string> = {
    document: '文档预览',
    ppt: 'PPT 预览',
    image: '图片预览',
    archive: '压缩包预览',
    code: '代码',
    workflow: 'Workflow',
    other: '文件',
  };
  return labels[kind] ?? kind;
}

function evaluationLabel(status: ArtifactEvaluationStatus) {
  const labels: Record<ArtifactEvaluationStatus, string> = {
    passed: '评估通过',
    failed: '评估失败',
    manual_review_required: '需人工复核',
    unknown: '评估未知',
  };
  return labels[status] ?? status;
}

function evaluationClassName(status: ArtifactEvaluationStatus) {
  if (status === 'passed') {
    return 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-400/25 dark:bg-emerald-950/20 dark:text-emerald-200';
  }
  if (status === 'failed') {
    return 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-400/25 dark:bg-rose-950/20 dark:text-rose-200';
  }
  if (status === 'manual_review_required') {
    return 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-400/25 dark:bg-amber-950/20 dark:text-amber-200';
  }
  return 'border-slate-300 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400';
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
