import { api } from '@/lib/api';

export interface DefectResponse {
  id: string;
  project_id: string;
  inspection_id: string | null;
  bim_element_guid: string | null;
  defect_class: string;
  severity: string;
  severity_score: number;
  confidence: number;
  bbox: Record<string, number>;
  source_image_url: string;
  annotated_image_url: string | null;
  world_position: Record<string, number> | null;
  dimensions: Record<string, number> | null;
  status: string;
  assigned_to_id: string | null;
  notes: string | null;
  remediation_recommendation: string | null;
  created_by_id: string;
  created_at: string;
  updated_at: string;
}

export interface DefectListResponse {
  defects: DefectResponse[];
  total: number;
  severity_summary: Record<string, number>;
}

export interface DefectStats {
  total: number;
  by_severity: Record<string, number>;
  by_class: Record<string, number>;
  by_status: Record<string, number>;
  avg_confidence: number;
  avg_severity_score: number;
}

export async function getDefects(params: {
  project_id: string;
  severity?: string;
  defect_class?: string;
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<DefectListResponse> {
  const query = new URLSearchParams();
  query.set('project_id', params.project_id);
  if (params.severity) query.set('severity', params.severity);
  if (params.defect_class) query.set('defect_class', params.defect_class);
  if (params.status) query.set('status', params.status);
  if (params.page) query.set('page', String(params.page));
  if (params.page_size) query.set('page_size', String(params.page_size));
  return api.get<DefectListResponse>(`/api/v1/defects/?${query.toString()}`);
}

export async function getDefect(id: string): Promise<DefectResponse> {
  return api.get<DefectResponse>(`/api/v1/defects/${id}`);
}

export async function updateDefect(
  id: string,
  data: Partial<{
    status: string;
    assigned_to_id: string;
    notes: string;
    severity: string;
    bim_element_guid: string;
    world_position: Record<string, number>;
  }>
): Promise<DefectResponse> {
  return api.put<DefectResponse>(`/api/v1/defects/${id}`, data);
}

export async function deleteDefect(id: string): Promise<void> {
  return api.del(`/api/v1/defects/${id}`);
}

export async function getDefectStats(projectId: string): Promise<DefectStats> {
  return api.get<DefectStats>(`/api/v1/defects/stats?project_id=${projectId}`);
}
