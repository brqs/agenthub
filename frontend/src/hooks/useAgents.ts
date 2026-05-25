import { useMemo } from 'react';
import { mockAgents } from '@/lib/mockData';

export function useAgents() {
  return useMemo(
    () => ({
      data: mockAgents,
      isLoading: false,
      error: null,
    }),
    [],
  );
}

