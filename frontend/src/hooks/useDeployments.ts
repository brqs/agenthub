import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as deploymentsAdapter from '@/lib/adapters/deployments';
import type { WorkspaceDeploymentRequest } from '@/lib/types';

function hasRunningDeployment(status: string): boolean {
  return status === 'queued' || status === 'publishing';
}

export function useDeployments(conversationId: string | null | undefined) {
  return useQuery({
    queryKey: ['workspace-deployments', conversationId],
    queryFn: () => deploymentsAdapter.listDeployments(conversationId as string),
    enabled: Boolean(conversationId),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => hasRunningDeployment(item.status)) ? 2_000 : false,
  });
}

export function useDeploymentStatus(
  conversationId: string | null | undefined,
  deploymentId: string | null | undefined,
) {
  return useQuery({
    queryKey: ['workspace-deployment', conversationId, deploymentId],
    queryFn: () =>
      deploymentsAdapter.getDeployment(conversationId as string, deploymentId as string),
    enabled: Boolean(conversationId) && Boolean(deploymentId),
    retry: false,
    refetchInterval: (query) =>
      query.state.data && hasRunningDeployment(query.state.data.status) ? 2_000 : false,
  });
}

export function useCreateDeployment(conversationId: string | null | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: WorkspaceDeploymentRequest) =>
      deploymentsAdapter.createDeployment(conversationId as string, payload),
    onSuccess: (deployment) => {
      queryClient.setQueryData(
        ['workspace-deployment', conversationId, deployment.id],
        deployment,
      );
      void queryClient.invalidateQueries({
        queryKey: ['workspace-deployments', conversationId],
      });
    },
  });
}

export function useStopDeployment(conversationId: string | null | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (deploymentId: string) =>
      deploymentsAdapter.stopDeployment(conversationId as string, deploymentId),
    onSuccess: (deployment) => {
      queryClient.setQueryData(
        ['workspace-deployment', conversationId, deployment.id],
        deployment,
      );
      void queryClient.invalidateQueries({
        queryKey: ['workspace-deployments', conversationId],
      });
    },
  });
}
