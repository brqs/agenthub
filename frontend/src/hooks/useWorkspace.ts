import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as workspacesAdapter from '@/lib/adapters/workspaces';
import { queryKeys } from '@/lib/queryKeys';
import { useAuthStore } from '@/stores/authStore';

export function useWorkspaceTree(conversationId: string | null | undefined) {
  return useQuery({
    queryKey: ['workspace-tree', conversationId],
    queryFn: () => workspacesAdapter.getWorkspaceTree(conversationId as string),
    enabled: Boolean(conversationId),
    retry: 2,
    retryDelay: 500,
  });
}

export function useWorkspaceFile(
  conversationId: string | null | undefined,
  path: string | null | undefined,
) {
  return useQuery({
    queryKey: ['workspace-file', conversationId, path],
    queryFn: () => workspacesAdapter.readWorkspaceFile(conversationId as string, path as string),
    enabled: Boolean(conversationId) && Boolean(path),
    retry: 2,
    retryDelay: 500,
  });
}

export function useWorkspaceArtifacts(
  conversationId: string | null | undefined,
  enabled = true,
) {
  const userId = useAuthStore((state) => state.user?.id);
  return useQuery({
    queryKey: queryKeys.workspaceArtifacts(userId, conversationId),
    queryFn: () => workspacesAdapter.listWorkspaceArtifacts(conversationId as string),
    enabled: enabled && Boolean(userId) && Boolean(conversationId),
    retry: false,
    staleTime: 30_000,
  });
}

export function useWriteWorkspaceFile(conversationId: string | null | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      path,
      content,
      mimeType,
    }: {
      path: string;
      content: string | Blob;
      mimeType?: string;
    }) =>
      workspacesAdapter.writeWorkspaceFile(
        conversationId as string,
        path,
        content,
        mimeType,
      ),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['workspace-tree', conversationId] });
      void queryClient.invalidateQueries({
        queryKey: ['workspace-file', conversationId, variables.path],
      });
    },
  });
}
