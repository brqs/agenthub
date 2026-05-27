import { api } from '@/lib/api';
import type {
  Agent,
  AgentList,
  CreateAgentRequest,
  UpdateAgentRequest,
} from '@/lib/types';
import { normalizeAgent } from './normalizers';

export interface ListAgentsParams {
  builtin?: boolean;
  provider?: Agent['provider'];
  page?: number;
  pageSize?: number;
}

export async function listAgents(params: ListAgentsParams = {}): Promise<Agent[]> {
  const { data } = await api.get<AgentList>('/api/v1/agents', {
    params: {
      builtin: params.builtin,
      provider: params.provider,
      page: params.page,
      page_size: params.pageSize,
    },
  });
  return data.items.map(normalizeAgent);
}

export async function createAgent(input: CreateAgentRequest): Promise<Agent> {
  const { data } = await api.post<Agent>('/api/v1/agents', input);
  return normalizeAgent(data);
}

export async function updateAgent(
  agentId: string,
  input: UpdateAgentRequest,
): Promise<Agent> {
  const { data } = await api.patch<Agent>(`/api/v1/agents/${agentId}`, input);
  return normalizeAgent(data);
}

export async function deleteAgent(agentId: string): Promise<void> {
  await api.delete(`/api/v1/agents/${agentId}`);
}
