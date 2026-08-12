import { api } from '@/lib/api';

export interface DetectionItem {
  defect_class: string;
  confidence: number;
  severity: string;
  severity_score: number;
  bbox: { x: number; y: number; w: number; h: number };
  bbox_pixels: { x1: number; y1: number; x2: number; y2: number };
  dimensions: { width_px: number; height_px: number; area_px: number };
}

export interface DetectionResponse {
  detections: DetectionItem[];
  detection_count: number;
  severity_summary: Record<string, number>;
  image_width: number;
  image_height: number;
  inference_time_ms: number;
  model_name: string;
  source_image_url: string;
  annotated_image_url: string | null;
}

export interface BatchDetectionStatus {
  task_id: string;
  status: string;
  total_images: number;
  processed_images: number;
  total_defects: number;
  severity_summary: Record<string, number>;
  progress_pct: number;
}

export interface DetectionConfig {
  confidence_threshold: number;
  model_name: string;
  device: string;
  supported_classes: string[];
  severity_levels: string[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function detectSingleImage(
  file: File,
  projectId: string,
  autoSave: boolean = true
): Promise<DetectionResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('project_id', projectId);
  formData.append('auto_save', String(autoSave));

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  const res = await fetch(`${API_BASE}/api/v1/detect/image`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Detection failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function detectBatch(
  files: File[],
  projectId: string
): Promise<BatchDetectionStatus> {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));
  formData.append('project_id', projectId);

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  const res = await fetch(`${API_BASE}/api/v1/detect/batch`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Batch detection failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function getDetectionConfig(): Promise<DetectionConfig> {
  return api.get<DetectionConfig>('/api/v1/detect/config');
}
