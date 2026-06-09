import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';
import { queryKeys } from '@/lib/queryKeys';
import type { CreateModelAccountRequest, UpdateModelAccountRequest } from '@/lib/types';
import { useAuthStore } from '@/stores/authStore';

export function useModelProviders() {
  return useQuery({
    queryKey: queryKeys.modelProviders(),
    queryFn: agentsAdapter.listModelProviders,
  });
}

export function useModelAccounts() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);
  const queryKey = queryKeys.modelAccounts(userId);

  const accounts = useQuery({
    queryKey,
    queryFn: agentsAdapter.listModelAccounts,
  });

  const create = useMutation({
    mutationFn: (input: CreateModelAccountRequest) => agentsAdapter.createModelAccount(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  const update = useMutation({
    mutationFn: ({ accountId, input }: { accountId: string; input: UpdateModelAccountRequest }) =>
      agentsAdapter.updateModelAccount(accountId, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  const remove = useMutation({
    mutationFn: (accountId: string) => agentsAdapter.deleteModelAccount(accountId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  const verify = useMutation({
    mutationFn: (accountId: string) => agentsAdapter.verifyModelAccount(accountId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  return { accounts, create, update, remove, verify };
}
