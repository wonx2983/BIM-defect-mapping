'use client';

import { create } from 'zustand';
import {
  getProjects,
  getProject,
  createProject,
  updateProject,
  deleteProject,
  type ProjectResponse,
} from '@/lib/api/projects';

interface ProjectState {
  projects: ProjectResponse[];
  currentProject: ProjectResponse | null;
  isLoading: boolean;
  total: number;
  error: string | null;
  fetchProjects: (params?: {
    search?: string;
    status?: string;
    page?: number;
  }) => Promise<void>;
  fetchProject: (id: string) => Promise<void>;
  addProject: (data: {
    name: string;
    description?: string;
    address?: string;
    client_name?: string;
  }) => Promise<void>;
  editProject: (
    id: string,
    data: Partial<{
      name: string;
      description: string;
      address: string;
      client_name: string;
      status: string;
    }>
  ) => Promise<void>;
  removeProject: (id: string) => Promise<void>;
}

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  currentProject: null,
  isLoading: false,
  total: 0,
  error: null,

  fetchProjects: async (params) => {
    set({ isLoading: true, error: null });
    try {
      const data = await getProjects(params);
      set({ projects: data.projects, total: data.total, isLoading: false });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load projects',
        isLoading: false,
      });
    }
  },

  fetchProject: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const project = await getProject(id);
      set({ currentProject: project, isLoading: false });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load project',
        isLoading: false,
      });
    }
  },

  addProject: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const project = await createProject(data);
      set((state) => ({
        projects: [project, ...state.projects],
        total: state.total + 1,
        isLoading: false,
      }));
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to create project',
        isLoading: false,
      });
      throw error;
    }
  },

  editProject: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await updateProject(id, data);
      set((state) => ({
        projects: state.projects.map((p) => (p.id === id ? updated : p)),
        currentProject: state.currentProject?.id === id ? updated : state.currentProject,
        isLoading: false,
      }));
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to update project',
        isLoading: false,
      });
      throw error;
    }
  },

  removeProject: async (id) => {
    try {
      await deleteProject(id);
      set((state) => ({
        projects: state.projects.filter((p) => p.id !== id),
        total: state.total - 1,
      }));
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to delete project',
      });
      throw error;
    }
  },
}));
