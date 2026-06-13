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
      error: string | null;
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
      error: string | null;
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
      error: string | null;
    };

export function buildReviewThreadItems(detail: OrchestratorRunDetail | null | undefined) {
  if (!detail) return [];
  const attemptsByTask = latestAttemptsByTask(detail.attempts);

  return sortReviewThreadTasks(
    detail.tasks.filter((task) => isReviewThreadTask(task)),
    attemptsByTask,
  )
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
          error: attempt?.error ?? null,
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
          error: attempt?.error ?? null,
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
        error: attempt?.error ?? null,
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

function sortReviewThreadTasks(
  tasks: OrchestratorTask[],
  attemptsByTask: Map<string, OrchestratorTaskAttempt>,
): OrchestratorTask[] {
  const byId = new Map(tasks.map((task) => [task.task_id, task]));
  const remaining = new Set(tasks.map((task) => task.task_id));
  const sorted: OrchestratorTask[] = [];

  while (remaining.size > 0) {
    const ready = [...remaining]
      .map((taskId) => byId.get(taskId))
      .filter((task): task is OrchestratorTask => Boolean(task))
      .filter((task) => dependenciesWithinThread(task, byId).every((dep) => !remaining.has(dep)))
      .sort((a, b) => chronologicalRank(a, attemptsByTask) - chronologicalRank(b, attemptsByTask));

    const next = ready[0] ?? byId.get([...remaining][0]);
    if (!next) break;
    sorted.push(next);
    remaining.delete(next.task_id);
  }

  return sorted;
}

function dependenciesWithinThread(
  task: OrchestratorTask,
  byId: Map<string, OrchestratorTask>,
): string[] {
  const refs = [...(task.depends_on ?? []), ...(task.review_of ?? [])];
  return refs.filter((taskId) => byId.has(taskId));
}

function chronologicalRank(
  task: OrchestratorTask,
  attemptsByTask: Map<string, OrchestratorTaskAttempt>,
): number {
  const attempt = attemptsByTask.get(task.task_id);
  const timestamp =
    attempt?.created_at ?? attempt?.completed_at ?? task.created_at ?? task.updated_at ?? '';
  const time = Date.parse(timestamp);
  const safeTime = Number.isFinite(time) ? time : 0;
  return safeTime * 1000 + (task.priority ?? 0);
}
