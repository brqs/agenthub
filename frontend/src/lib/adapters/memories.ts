import { api } from '@/lib/api';
import type {
  Memory,
  ConversationMemoryHub,
  MemoryList,
  MemoryMountList,
  UpdateMemoryRequest,
} from '@/lib/types';

export type MemoryScopeType = Memory['scope_type'];
export type MemoryKind = Memory['kind'];
export type MemoryStatus = Memory['status'];

export async function listMemories(params: {
  scopeType?: MemoryScopeType;
  scopeId?: string;
  kind?: MemoryKind;
  status?: MemoryStatus;
  limit?: number;
} = {}): Promise<MemoryList> {
  const { data } = await api.get<MemoryList>('/api/v1/memories', {
    params: {
      scope_type: params.scopeType,
      scope_id: params.scopeId,
      kind: params.kind,
      status: params.status,
      limit: params.limit,
    },
  });
  return data;
}

export async function updateMemory(memoryId: string, payload: UpdateMemoryRequest): Promise<Memory> {
  const { data } = await api.patch<Memory>(`/api/v1/memories/${memoryId}`, payload);
  return data;
}

export async function forgetMemory(memoryId: string): Promise<Memory> {
  const { data } = await api.delete<Memory>(`/api/v1/memories/${memoryId}`);
  return data;
}

export async function listConversationMemoryMounts(
  conversationId: string,
  limit = 50,
): Promise<MemoryMountList> {
  const { data } = await api.get<MemoryMountList>(
    `/api/v1/conversations/${conversationId}/memory-mounts`,
    { params: { limit } },
  );
  return data;
}

export async function getConversationMemoryHub(
  conversationId: string,
): Promise<ConversationMemoryHub> {
  const { data } = await api.get<ConversationMemoryHub>(
    `/api/v1/conversations/${conversationId}/memory-hub`,
  );
  return data;
}
