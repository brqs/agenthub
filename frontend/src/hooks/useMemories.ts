import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  forgetMemory,
  getConversationMemoryHub,
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

export function useConversationMemoryHub(conversationId: string | null | undefined) {
  return useQuery({
    queryKey: ['conversation-memory-hub', conversationId],
    queryFn: () => getConversationMemoryHub(conversationId as string),
    enabled: Boolean(conversationId),
    retry: 1,
  });
}

export function useUpdateMemory(conversationId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ memoryId, payload }: { memoryId: string; payload: UpdateMemoryRequest }) =>
      updateMemory(memoryId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['memories'] });
      void queryClient.invalidateQueries({ queryKey: ['memory-mounts'] });
      if (conversationId) {
        void queryClient.invalidateQueries({
          queryKey: ['conversation-memory-hub', conversationId],
        });
      }
    },
  });
}

export function useForgetMemory(conversationId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: forgetMemory,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['memories'] });
      void queryClient.invalidateQueries({ queryKey: ['memory-mounts'] });
      if (conversationId) {
        void queryClient.invalidateQueries({
          queryKey: ['conversation-memory-hub', conversationId],
        });
      }
    },
  });
}
