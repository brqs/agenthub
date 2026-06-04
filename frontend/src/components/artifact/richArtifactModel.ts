import type { WorkspaceArtifact, ArtifactEvaluationStatus } from '@/lib/adapters/workspaces';
import type { FileBlock } from '@/lib/types';

export interface RichArtifactViewModel {
  path: string | null;
  artifactKind: NonNullable<FileBlock['artifact_kind']>;
  filename: string;
  url: string;
  size: number;
  mimeType: string;
  agentId?: string | null;
  taskId?: string | null;
  runId?: string | null;
  previewText?: string | null;
  previewTruncated?: boolean | null;
  metadata: Record<string, unknown>;
  evaluationStatus: ArtifactEvaluationStatus;
  evaluationResults: Array<Record<string, unknown>>;
}

export function indexArtifactsByPath(
  artifacts: WorkspaceArtifact[] | null | undefined,
): Map<string, WorkspaceArtifact> {
  const index = new Map<string, WorkspaceArtifact>();
  for (const artifact of artifacts ?? []) {
    const existing = index.get(artifact.path);
    if (!existing || artifact.updated_at.localeCompare(existing.updated_at) >= 0) {
      index.set(artifact.path, artifact);
    }
  }
  return index;
}

export function buildRichArtifactViewModel(
  block: FileBlock,
  manifestArtifact?: WorkspaceArtifact | null,
): RichArtifactViewModel {
  return {
    path: manifestArtifact?.path ?? block.path ?? null,
    artifactKind: manifestArtifact?.artifact_kind ?? block.artifact_kind ?? 'other',
    filename: manifestArtifact?.filename ?? block.filename,
    url: manifestArtifact?.url ?? block.url,
    size: manifestArtifact?.size ?? block.size,
    mimeType: manifestArtifact?.mime_type ?? block.mime_type,
    agentId: manifestArtifact?.agent_id ?? block.agent_id ?? null,
    taskId: manifestArtifact?.task_id ?? null,
    runId: manifestArtifact?.run_id ?? null,
    previewText: manifestArtifact?.preview_text ?? block.preview_text ?? null,
    previewTruncated: manifestArtifact?.preview_truncated ?? block.preview_truncated ?? null,
    metadata: {
      ...(block.metadata ?? {}),
      ...(manifestArtifact?.metadata ?? {}),
    },
    evaluationStatus: manifestArtifact?.evaluation_status ?? 'unknown',
    evaluationResults: manifestArtifact?.evaluation_results ?? [],
  };
}
