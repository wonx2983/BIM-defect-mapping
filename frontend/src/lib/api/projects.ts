import { api } from '@/lib/api';

export interface ProjectResponse {
  id: string;
  name: string;
  description: string | null;
  address: string | null;
  client_name: string | null;
  organization_id: string;
  created_by_id: string;
  status: string;
  defect_count: number;
  bim_model_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  projects: ProjectResponse[];
  total: number;
}

export async function getProjects(params?: {
  search?: string;
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<ProjectListResponse> {
  const query = new URLSearchParams();
  if (params?.search) query.set('search', params.search);
  if (params?.status) query.set('status', params.status);
  if (params?.page) query.set('page', String(params.page));
  if (params?.page_size) query.set('page_size', String(params.page_size));
  const qs = query.toString();
  return api.get<ProjectListResponse>(`/api/v1/projects/${qs ? `?${qs}` : ''}`);
}

export async function getProject(id: string): Promise<ProjectResponse> {
  return api.get<ProjectResponse>(`/api/v1/projects/${id}`);
}

export async function createProject(data: {
  name: string;
  description?: string;
  address?: string;
  client_name?: string;
}): Promise<ProjectResponse> {
  return api.post<ProjectResponse>('/api/v1/projects/', data);
}

export async function updateProject(
  id: string,
  data: Partial<{ name: string; description: string; address: string; client_name: string; status: string }>
): Promise<ProjectResponse> {
  return api.put<ProjectResponse>(`/api/v1/projects/${id}`, data);
}

export async function deleteProject(id: string): Promise<void> {
  return api.del(`/api/v1/projects/${id}`);
}
