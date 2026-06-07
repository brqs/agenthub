import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  forgetMemory,
  listConversationMemoryMounts,
  listMemories,
  updateMemory,
  type MemoryStatus,
} from '@/lib/adapters/memories';
import type { UpdateMemoryRequest } from '@/lib/types';

export function useMemories(status?: MemoryStatus) {
  return useQuery({
    queryKey: ['memories', status ?? 'all'],
    queryFn: () => listMemories({ status, limit: 100 }),
    retry: 1,
  });
}

export function useConversationMemoryMounts(conversationId: string | null | undefined) {
  return useQuery({
    queryKey: ['memory-mounts', conversationId],
    queryFn: () => listConversationMemoryMounts(conversationId as string),
    enabled: Boolean(conversationId),
    retry: 1,
  });
}

export function useUpdateMemory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ memoryId, payload }: { memoryId: string; payload: UpdateMemoryRequest }) =>
      updateMemory(memoryId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['memories'] });
      void queryClient.invalidateQueries({ queryKey: ['memory-mounts'] });
    },
  });
}

export function useForgetMemory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: forgetMemory,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['memories'] });
      void queryClient.invalidateQueries({ queryKey: ['memory-mounts'] });
    },
  });
}
