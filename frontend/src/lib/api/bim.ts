import { api } from '@/lib/api';

export interface BIMModel {
  id: string;
  project_id: string;
  original_filename: string;
  file_url: string;
  file_size_bytes: number;
  processing_status: string;
  element_count: number | null;
  uploaded_by_id: string;
  created_at: string;
  updated_at: string;
}

export interface MappedDefectsResponse {
  mapped: Array<{
    id: string;
    defect_class: string;
    severity: string;
    severity_score: number;
    confidence: number;
    bim_element_guid: string | null;
    world_position: { x: number; y: number; z: number } | null;
    status: string;
    notes: string | null;
    created_at: string;
    source_image_url: string;
  }>;
  unmapped: Array<{
    id: string;
    defect_class: string;
    severity: string;
    severity_score: number;
    confidence: number;
    status: string;
    notes: string | null;
    created_at: string;
    source_image_url: string;
  }>;
  mapped_count: number;
  unmapped_count: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function getBIMModels(projectId: string): Promise<{ models: BIMModel[]; total: number }> {
  return api.get(`/api/v1/bim/${projectId}/models`);
}

export async function uploadBIMModel(projectId: string, file: File): Promise<BIMModel> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('project_id', projectId);

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch(`${API_BASE}/api/v1/bim/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function deleteBIMModel(modelId: string): Promise<void> {
  return api.del(`/api/v1/bim/model/${modelId}`);
}

export async function getMappedDefects(projectId: string): Promise<MappedDefectsResponse> {
  return api.get(`/api/v1/bim/${projectId}/defects-mapped`);
}
