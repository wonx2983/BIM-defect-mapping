'use client';

import { create } from 'zustand';
import {
  login as apiLogin,
  register as apiRegister,
  getMe,
  type UserResponse,
  type TokenResponse,
} from '@/lib/api/auth';

interface AuthState {
  user: UserResponse | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: {
    email: string;
    password: string;
    full_name: string;
    organization_name: string;
  }) => Promise<void>;
  logout: () => void;
  loadUser: () => Promise<void>;
  setTokens: (tokens: TokenResponse) => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken:
    typeof window !== 'undefined' ? localStorage.getItem('access_token') : null,
  refreshToken:
    typeof window !== 'undefined' ? localStorage.getItem('refresh_token') : null,
  isAuthenticated:
    typeof window !== 'undefined' ? !!localStorage.getItem('access_token') : false,
  isLoading: false,

  setTokens: (tokens) => {
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
    set({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      isAuthenticated: true,
    });
  },

  login: async (email, password) => {
    set({ isLoading: true });
    try {
      const tokens = await apiLogin(email, password);
      get().setTokens(tokens);
      const user = await getMe();
      set({ user, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  register: async (data) => {
    set({ isLoading: true });
    try {
      const tokens = await apiRegister(data);
      get().setTokens(tokens);
      const user = await getMe();
      set({ user, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
  },

  loadUser: async () => {
    if (!get().accessToken) return;
    set({ isLoading: true });
    try {
      const user = await getMe();
      set({ user, isLoading: false });
    } catch {
      get().logout();
      set({ isLoading: false });
    }
  },
}));
