import { useQuery } from '@tanstack/react-query';
import * as agentsAdapter from '@/lib/adapters/agents';

export function useAgentTemplates() {
  return useQuery({
    queryKey: ['agent-templates'],
    queryFn: () => agentsAdapter.listAgentTemplates(),
    staleTime: 5 * 60 * 1000,
  });
}
