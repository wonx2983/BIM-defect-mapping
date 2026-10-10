import { api } from '@/lib/api';

/* ── Fiducial Marker Types ─────────────────────────────────────────── */

export interface FiducialMarker {
  id: string;
  project_id: string;
  marker_dict_id: number;
  aruco_dict_type: string;
  bim_model_id: string | null;
  bim_element_guid: string | null;
  bim_point_description: string | null;
  world_x: number;
  world_y: number;
  world_z: number;
  normal_x: number;
  normal_y: number;
  normal_z: number;
  physical_size_m: number;
  created_by_id: string;
  created_at: string;
  updated_at: string;
}

export interface MarkerCreateData {
  project_id: string;
  marker_dict_id: number;
  aruco_dict_type?: string;
  bim_model_id?: string;
  bim_element_guid?: string;
  bim_point_description?: string;
  world_x: number;
  world_y: number;
  world_z: number;
  normal_x?: number;
  normal_y?: number;
  normal_z?: number;
  physical_size_m: number;
}

/* ── Calibration Types ─────────────────────────────────────────────── */

export interface CalibrationResult {
  success: boolean;
  calibration_status: string;
  marker_id: number | null;
  marker_registry_id: string | null;
  reprojection_error_px: number | null;
  camera_position: { x: number; y: number; z: number } | null;
  candidate_element_count: number | null;
  message: string;
}

export interface CalibrationStatus {
  camera_id: string;
  camera_name: string;
  calibration_status: string;
  calibration_error_px: number | null;
  calibrated_at: string | null;
  calibrated_with_marker_id: string | null;
  has_intrinsics: boolean;
  has_pose: boolean;
  candidate_element_count: number;
  camera_position: { x: number; y: number; z: number } | null;
}

export interface AutoMappingResult {
  camera_id: string;
  camera_name: string;
  frames_analyzed: number;
  total_detections: number;
  mapped_count: number;
  deduplicated_count: number;
  unmapped_count: number;
  results: Array<{
    defect_class: string;
    confidence: number;
    severity: string;
    mapped_element_guid: string | null;
    hit_position: { x: number; y: number; z: number } | null;
    hit_distance_m: number | null;
    was_deduplicated: boolean;
    defect_id: string | null;
  }>;
  status: string;
}

/* ── Marker API ────────────────────────────────────────────────────── */

export async function getMarkers(
  projectId: string,
): Promise<{ markers: FiducialMarker[]; total: number }> {
  return api.get(`/api/v1/markers/?project_id=${projectId}`);
}

export async function createMarker(
  data: MarkerCreateData,
): Promise<FiducialMarker> {
  return api.post('/api/v1/markers/', data);
}

export async function updateMarker(
  id: string,
  data: Record<string, unknown>,
): Promise<FiducialMarker> {
  return api.put(`/api/v1/markers/${id}`, data);
}

export async function deleteMarker(id: string): Promise<void> {
  return api.del(`/api/v1/markers/${id}`);
}

/* ── Calibration API ───────────────────────────────────────────────── */

export async function calibrateCamera(
  cameraId: string,
  data: {
    fov_horizontal_deg?: number;
    image_width?: number;
    image_height?: number;
  } = {},
): Promise<CalibrationResult> {
  return api.post(`/api/v1/calibration/${cameraId}/calibrate`, data);
}

export async function getCalibrationStatus(
  cameraId: string,
): Promise<CalibrationStatus> {
  return api.get(`/api/v1/calibration/${cameraId}/status`);
}

export async function runAutoMappedDetection(
  cameraId: string,
  maxFrames = 50,
): Promise<AutoMappingResult> {
  return api.post(
    `/api/v1/calibration/${cameraId}/auto-detect?max_frames=${maxFrames}`,
  );
}
