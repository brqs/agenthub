import { api } from '@/lib/api';
import type {
  AuthResponse,
  LoginRequest,
  RegisterRequest,
  UserSessionList,
  UpdateSessionRequest,
  User,
} from '@/lib/types';

export async function login(input: LoginRequest): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/api/v1/auth/login', input);
  return data;
}

export async function register(input: RegisterRequest): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/api/v1/auth/register', input);
  return data;
}

export async function getCurrentUser(): Promise<User> {
  const { data } = await api.get<User>('/api/v1/auth/me');
  return data;
}

export async function logout(refreshToken?: string | null): Promise<void> {
  await api.post('/api/v1/auth/logout', { refresh_token: refreshToken ?? null });
}

export async function listSessions(): Promise<UserSessionList> {
  const { data } = await api.get<UserSessionList>('/api/v1/auth/sessions');
  return data;
}

export async function updateSession(sessionId: string, input: UpdateSessionRequest): Promise<void> {
  await api.patch(`/api/v1/auth/sessions/${sessionId}`, input);
}

export async function revokeSession(sessionId: string): Promise<void> {
  await api.delete(`/api/v1/auth/sessions/${sessionId}`);
}

export async function revokeOtherSessions(): Promise<void> {
  await api.delete('/api/v1/auth/sessions');
}
