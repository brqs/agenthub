import type {
  OrchestratorRunDetail,
  OrchestratorTask,
  OrchestratorTaskAttempt,
} from '@/lib/types';

export type ReviewThreadItem =
  | {
      kind: 'implementation';
      taskId: string;
      agentId: string;
      title: string;
      state: string;
      artifactPaths: string[];
      summary: string;
    }
  | {
      kind: 'review';
      taskId: string;
      agentId: string;
      title: string;
      state: string;
      reviewOf: string[];
      outcome: string;
      summary: string;
    }
  | {
      kind: 'repair';
      taskId: string;
      agentId: string;
      title: string;
      state: string;
      reviewOf: string[];
      handoffReason?: string | null;
      summary: string;
    };

export function buildReviewThreadItems(detail: OrchestratorRunDetail | null | undefined) {
  if (!detail) return [];
  const attemptsByTask = latestAttemptsByTask(detail.attempts);

  return detail.tasks
    .filter((task) => isReviewThreadTask(task))
    .sort((a, b) => a.priority - b.priority || a.created_at.localeCompare(b.created_at))
    .map((task): ReviewThreadItem => {
      const attempt = attemptsByTask.get(task.task_id);
      if (task.task_type === 'review') {
        return {
          kind: 'review',
          taskId: task.task_id,
          agentId: task.agent_id,
          title: task.title,
          state: attempt?.state ?? task.final_state,
          reviewOf: task.review_of ?? [],
          outcome: attempt?.review_outcome ?? 'unknown',
          summary: attempt?.text_preview ?? '',
        };
      }
      if (task.task_type === 'repair') {
        return {
          kind: 'repair',
          taskId: task.task_id,
          agentId: task.agent_id,
          title: task.title,
          state: attempt?.state ?? task.final_state,
          reviewOf: task.review_of ?? [],
          handoffReason: task.handoff_reason ?? null,
          summary: attempt?.text_preview ?? '',
        };
      }
      return {
        kind: 'implementation',
        taskId: task.task_id,
        agentId: task.agent_id,
        title: task.title,
        state: attempt?.state ?? task.final_state,
        artifactPaths: attempt?.artifact_paths ?? [],
        summary: attempt?.text_preview ?? '',
      };
    });
}

function isReviewThreadTask(task: OrchestratorTask): boolean {
  return (
    task.task_type === 'implementation' ||
    task.task_type === 'review' ||
    task.task_type === 'repair'
  );
}

function latestAttemptsByTask(
  attempts: OrchestratorTaskAttempt[],
): Map<string, OrchestratorTaskAttempt> {
  const map = new Map<string, OrchestratorTaskAttempt>();
  for (const attempt of attempts) {
    const existing = map.get(attempt.task_id);
    if (!existing || attempt.attempt_index >= existing.attempt_index) {
      map.set(attempt.task_id, attempt);
    }
  }
  return map;
}
