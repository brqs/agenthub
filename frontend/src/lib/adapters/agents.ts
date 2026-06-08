import { api } from '@/lib/api';
import type {
  Agent,
  AgentAssetHistoryResponse,
  AgentAssetsResponse,
  AgentAssetUsageResponse,
  AgentMcpHealth,
  CreateModelAccountRequest,
  AgentKnowledgeRef,
  AgentKnowledgeUsage,
  AgentSkillRef,
  AgentTemplateList,
  AgentTestRunResponse,
  AgentList,
  ModelAccount,
  ModelAccountList,
  ModelAccountVerifyResponse,
  ModelProviderList,
  CreateAgentRequest,
  UpdateModelAccountRequest,
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

export async function listAgentTemplates(): Promise<AgentTemplateList> {
  const { data } = await api.get<AgentTemplateList>('/api/v1/agents/templates');
  return data;
}

export async function listModelProviders(): Promise<ModelProviderList> {
  const { data } = await api.get<ModelProviderList>('/api/v1/model-providers');
  return data;
}

export async function listModelAccounts(): Promise<ModelAccountList> {
  const { data } = await api.get<ModelAccountList>('/api/v1/model-accounts');
  return data;
}

export async function createModelAccount(input: CreateModelAccountRequest): Promise<ModelAccount> {
  const { data } = await api.post<ModelAccount>('/api/v1/model-accounts', input);
  return data;
}

export async function updateModelAccount(
  accountId: string,
  input: UpdateModelAccountRequest,
): Promise<ModelAccount> {
  const { data } = await api.patch<ModelAccount>(`/api/v1/model-accounts/${accountId}`, input);
  return data;
}

export async function deleteModelAccount(accountId: string): Promise<void> {
  await api.delete(`/api/v1/model-accounts/${accountId}`);
}

export async function verifyModelAccount(
  accountId: string,
): Promise<ModelAccountVerifyResponse> {
  const { data } = await api.post<ModelAccountVerifyResponse>(
    `/api/v1/model-accounts/${accountId}/verify`,
  );
  return data;
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

export async function checkAgentMcpHealth(agentId: string): Promise<AgentMcpHealth> {
  const { data } = await api.post<AgentMcpHealth>(`/api/v1/agents/${agentId}/mcp/health-check`);
  return data;
}

export async function testRunAgent(agentId: string, prompt: string): Promise<AgentTestRunResponse> {
  const { data } = await api.post<AgentTestRunResponse>(`/api/v1/agents/${agentId}/test-run`, {
    prompt,
  });
  return data;
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
