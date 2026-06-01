import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as deploymentsAdapter from '@/lib/adapters/deployments';

export function useDeployments(conversationId: string | null | undefined) {
  return useQuery({
    queryKey: ['workspace-deployments', conversationId],
    queryFn: () => deploymentsAdapter.listDeployments(conversationId as string),
    enabled: Boolean(conversationId),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => item.status === 'publishing') ? 2_000 : false,
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
    refetchInterval: (query) => (query.state.data?.status === 'publishing' ? 2_000 : false),
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
