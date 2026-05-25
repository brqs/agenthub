import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import * as authAdapter from '@/lib/adapters/auth';
import { env } from '@/lib/env';
import { MOCK_DEMO_TOKEN } from '@/pages/LoginPage';
import { useAuthStore } from '@/stores/authStore';

/**
 * Gates routes behind a token. In API mode, also pings `/auth/me` on mount to
 * validate the persisted token and refresh the cached user. A stale/invalid
 * token surfaces as 401, which `api.ts` already converts to logout + redirect.
 *
 * If the persisted token is the magic mock-demo token but we're now running
 * against the real backend, drop it locally before any request — otherwise
 * the user sees a flash of 401 before being bounced to /login.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const setUser = useAuthStore((s) => s.setUser);
  const logout = useAuthStore((s) => s.logout);
  const location = useLocation();

  const isZombieDemoToken = !env.useMockApi && token === MOCK_DEMO_TOKEN;

  useEffect(() => {
    if (isZombieDemoToken) logout();
  }, [isZombieDemoToken, logout]);

  const meQuery = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: authAdapter.getCurrentUser,
    enabled: !env.useMockApi && Boolean(token) && !isZombieDemoToken,
    retry: false,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (meQuery.data) setUser(meQuery.data);
  }, [meQuery.data, setUser]);

  if (!token || isZombieDemoToken) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}
