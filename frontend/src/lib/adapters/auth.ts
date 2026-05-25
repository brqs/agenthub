import { api } from '@/lib/api';
import type {
  AuthResponse,
  LoginRequest,
  RegisterRequest,
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
