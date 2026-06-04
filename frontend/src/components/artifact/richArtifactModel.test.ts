import { buildRichArtifactViewModel, indexArtifactsByPath } from './richArtifactModel';
import type { WorkspaceArtifact } from '@/lib/adapters/workspaces';
import type { FileBlock } from '@/lib/types';

const fileBlock: FileBlock = {
  type: 'file',
  agent_id: 'codex-helper',
  path: 'docs/report.md',
  artifact_kind: 'document',
  filename: 'report.md',
  url: '/api/v1/workspaces/conv/files/docs/report.md',
  size: 100,
  mime_type: 'text/markdown',
  preview_text: '# Draft',
  preview_truncated: false,
  metadata: { section_count: 2 },
};

function artifact(overrides: Partial<WorkspaceArtifact> = {}): WorkspaceArtifact {
  return {
    path: 'docs/report.md',
    artifact_kind: 'document',
    filename: 'report.md',
    size: 128,
    mime_type: 'text/markdown',
    url: '/api/v1/workspaces/conv/files/docs/report.md',
    agent_id: 'claude-code',
    task_id: 'task-report',
    run_id: 'run-1',
    preview_text: '# Final',
    preview_truncated: false,
    metadata: { section_count: 3 },
    evaluation_status: 'passed',
    evaluation_results: [{ checker: 'document_quality' }],
    created_at: '2026-06-03T12:00:00Z',
    updated_at: '2026-06-03T12:00:00Z',
    ...overrides,
  };
}

describe('richArtifactModel', () => {
  it('merges manifest metadata over persisted file block basics', () => {
    expect(buildRichArtifactViewModel(fileBlock, artifact())).toMatchObject({
      path: 'docs/report.md',
      agentId: 'claude-code',
      taskId: 'task-report',
      runId: 'run-1',
      previewText: '# Final',
      metadata: { section_count: 3 },
      evaluationStatus: 'passed',
    });
  });

  it('falls back to the file block when manifest is unavailable', () => {
    expect(buildRichArtifactViewModel(fileBlock, null)).toMatchObject({
      path: 'docs/report.md',
      agentId: 'codex-helper',
      previewText: '# Draft',
      evaluationStatus: 'unknown',
    });
  });

  it('indexes duplicate paths by the newest updated_at', () => {
    const older = artifact({ size: 1, updated_at: '2026-06-03T12:00:00Z' });
    const newer = artifact({ size: 2, updated_at: '2026-06-03T12:01:00Z' });

    expect(indexArtifactsByPath([older, newer]).get('docs/report.md')?.size).toBe(2);
  });
});
