import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as workspacesAdapter from '@/lib/adapters/workspaces';
import { env } from '@/lib/env';

export function useWorkspaceTree(conversationId: string | null | undefined) {
  return useQuery({
    queryKey: ['workspace-tree', conversationId],
    queryFn: () => workspacesAdapter.getWorkspaceTree(conversationId as string),
    enabled: Boolean(conversationId) && !env.useMockApi,
    retry: false,
  });
}

export function useWorkspaceFile(
  conversationId: string | null | undefined,
  path: string | null | undefined,
) {
  return useQuery({
    queryKey: ['workspace-file', conversationId, path],
    queryFn: () => workspacesAdapter.readWorkspaceFile(conversationId as string, path as string),
    enabled: Boolean(conversationId) && Boolean(path) && !env.useMockApi,
    retry: false,
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
