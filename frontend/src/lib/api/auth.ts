import { api } from '@/lib/api';

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  role: string;
  organization_id: string;
  is_active: boolean;
  created_at: string;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  return api.post<TokenResponse>('/api/v1/auth/login', { email, password });
}

export async function register(data: {
  email: string;
  password: string;
  full_name: string;
  organization_name: string;
}): Promise<TokenResponse> {
  return api.post<TokenResponse>('/api/v1/auth/register', data);
}

export async function refreshToken(token: string): Promise<TokenResponse> {
  return api.post<TokenResponse>('/api/v1/auth/refresh', { refresh_token: token });
}

export async function getMe(): Promise<UserResponse> {
  return api.get<UserResponse>('/api/v1/auth/me');
}
