import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import * as authAdapter from '@/lib/adapters/auth';
import { queryKeys } from '@/lib/queryKeys';
import { useAuthStore } from '@/stores/authStore';

/**
 * Gates routes behind a token. Also pings `/auth/me` on mount to
 * validate the persisted token and refresh the cached user. A stale/invalid
 * token surfaces as 401, which `api.ts` already converts to logout + redirect.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const setUser = useAuthStore((s) => s.setUser);
  const location = useLocation();

  const meQuery = useQuery({
    queryKey: queryKeys.authMe(token),
    queryFn: authAdapter.getCurrentUser,
    enabled: Boolean(token),
    retry: false,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (meQuery.data) setUser(meQuery.data);
  }, [meQuery.data, setUser]);

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}
