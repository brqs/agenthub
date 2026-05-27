import { useQuery } from '@tanstack/react-query';
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
