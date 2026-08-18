import { api } from '@/lib/api';

export interface Camera {
  id: string;
  project_id: string;
  name: string;
  rtsp_url: string;
  bim_model_id: string | null;
  bim_element_guid: string | null;
  bim_zone_label: string | null;
  world_position: { x: number; y: number; z: number } | null;
  location_description: string | null;
  status: string;
  is_active: boolean;
  frame_skip: number;
  auto_detect_enabled: boolean;
  auto_detect_interval_minutes: number;
  last_detection_at: string | null;
  total_defects_found: number;
  created_at: string;
}

export interface CameraDetectionResult {
  camera_id: string;
  camera_name: string;
  frames_analyzed: number;
  total_detections: number;
  unique_defects_saved: number;
  bim_element_guid: string | null;
  bim_zone: string | null;
  defects: Array<{
    defect_class: string;
    severity: string;
    confidence: number;
    bim_element_guid: string | null;
    bim_zone: string | null;
  }>;
  status: string;
}

export async function getCameras(projectId: string): Promise<{ cameras: Camera[]; total: number }> {
  return api.get(`/api/v1/cameras/?project_id=${projectId}`);
}

export async function createCamera(data: {
  name: string;
  rtsp_url: string;
  project_id: string;
  bim_model_id?: string;
  bim_element_guid?: string;
  bim_zone_label?: string;
  world_position?: { x: number; y: number; z: number };
  location_description?: string;
  frame_skip?: number;
  auto_detect_enabled?: boolean;
  auto_detect_interval_minutes?: number;
}): Promise<Camera> {
  return api.post('/api/v1/cameras/', data);
}

export async function updateCamera(id: string, data: Record<string, unknown>): Promise<Camera> {
  return api.put(`/api/v1/cameras/${id}`, data);
}

export async function deleteCamera(id: string): Promise<void> {
  return api.del(`/api/v1/cameras/${id}`);
}

export async function runCameraDetection(id: string, maxFrames = 50): Promise<CameraDetectionResult> {
  return api.post(`/api/v1/cameras/${id}/detect?max_frames=${maxFrames}`);
}
