import { api } from '@/lib/api';
import type { OrchestratorRunDetail, OrchestratorRunList } from '@/lib/types';

export async function listOrchestratorRuns(
  conversationId: string,
  limit = 20,
): Promise<OrchestratorRunList> {
  const { data } = await api.get<OrchestratorRunList>(
    `/api/v1/conversations/${conversationId}/orchestrator-runs`,
    { params: { limit } },
  );
  return data;
}

export async function getOrchestratorRunDetail(
  conversationId: string,
  runId: string,
): Promise<OrchestratorRunDetail> {
  const { data } = await api.get<OrchestratorRunDetail>(
    `/api/v1/conversations/${conversationId}/orchestrator-runs/${runId}`,
  );
  return data;
}
