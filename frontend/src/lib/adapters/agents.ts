import { api } from '@/lib/api';
import type {
  Agent,
  AgentAssetHistoryResponse,
  AgentAssetsResponse,
  AgentAssetUsageResponse,
  AgentKnowledgeRef,
  AgentKnowledgeUsage,
  AgentSkillRef,
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

export async function updateAgent(agentId: string, input: UpdateAgentRequest): Promise<Agent> {
  const { data } = await api.patch<Agent>(`/api/v1/agents/${agentId}`, input);
  return normalizeAgent(data);
}

export async function deleteAgent(agentId: string): Promise<void> {
  await api.delete(`/api/v1/agents/${agentId}`);
}

export async function listAgentAssets(agentId: string): Promise<AgentAssetsResponse> {
  const { data } = await api.get<AgentAssetsResponse>(`/api/v1/agents/${agentId}/assets`);
  return data;
}

export async function listAgentAssetHistory(
  agentId: string,
  limit = 50,
): Promise<AgentAssetHistoryResponse> {
  const { data } = await api.get<AgentAssetHistoryResponse>(
    `/api/v1/agents/${agentId}/assets/history`,
    { params: { limit } },
  );
  return data;
}

export async function listAgentAssetUsage(
  agentId: string,
  limit = 50,
): Promise<AgentAssetUsageResponse> {
  const { data } = await api.get<AgentAssetUsageResponse>(
    `/api/v1/agents/${agentId}/assets/usage`,
    { params: { limit } },
  );
  return data;
}

export async function uploadAgentKnowledge(input: {
  agentId: string;
  file: File;
  label?: string;
  usage?: AgentKnowledgeUsage;
}): Promise<AgentKnowledgeRef> {
  const formData = new FormData();
  formData.append('file', input.file, input.file.name);
  if (input.label) formData.append('label', input.label);
  formData.append('usage', input.usage ?? 'reference');
  const { data } = await api.post<AgentKnowledgeRef>(
    `/api/v1/agents/${input.agentId}/knowledge`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return data;
}

export async function deleteAgentKnowledge(agentId: string, uploadId: string): Promise<void> {
  await api.delete(`/api/v1/agents/${agentId}/knowledge/${uploadId}`);
}

export async function updateAgentKnowledge(
  agentId: string,
  uploadId: string,
  input: { label?: string; usage?: AgentKnowledgeUsage },
): Promise<AgentKnowledgeRef> {
  const { data } = await api.patch<AgentKnowledgeRef>(
    `/api/v1/agents/${agentId}/knowledge/${uploadId}`,
    input,
  );
  return data;
}

export async function uploadAgentSkill(input: {
  agentId: string;
  file: File;
  name?: string;
  description?: string;
}): Promise<AgentSkillRef> {
  const formData = new FormData();
  formData.append('file', input.file, input.file.name);
  if (input.name) formData.append('name', input.name);
  if (input.description) formData.append('description', input.description);
  const { data } = await api.post<AgentSkillRef>(
    `/api/v1/agents/${input.agentId}/skills`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return data;
}

export async function deleteAgentSkill(agentId: string, skillId: string): Promise<void> {
  await api.delete(`/api/v1/agents/${agentId}/skills/${skillId}`);
}

export async function updateAgentSkill(
  agentId: string,
  skillId: string,
  input: { name?: string; description?: string },
): Promise<AgentSkillRef> {
  const { data } = await api.patch<AgentSkillRef>(
    `/api/v1/agents/${agentId}/skills/${skillId}`,
    input,
  );
  return data;
}
