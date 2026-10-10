"""Calibration & fiducial marker request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Fiducial Marker Schemas ──────────────────────────────────────────

class MarkerCreate(BaseModel):
    """Register a new fiducial marker at a known BIM coordinate."""

    project_id: uuid.UUID
    marker_dict_id: int = Field(
        ..., ge=0, description="ArUco marker ID from the printed pattern",
    )
    aruco_dict_type: str = Field(
        default="DICT_4X4_50",
        description="OpenCV ArUco dictionary name",
    )
    bim_model_id: uuid.UUID | None = None
    bim_element_guid: str | None = Field(
        default=None,
        description="GUID of the BIM element the marker is attached to",
    )
    bim_point_description: str | None = Field(
        default=None,
        description="Human-readable placement description",
    )
    world_x: float = Field(..., description="X coordinate in BIM world space (metres)")
    world_y: float = Field(..., description="Y coordinate in BIM world space (metres)")
    world_z: float = Field(..., description="Z coordinate in BIM world space (metres)")
    normal_x: float = Field(default=0.0, description="Surface normal X")
    normal_y: float = Field(default=0.0, description="Surface normal Y")
    normal_z: float = Field(default=1.0, description="Surface normal Z")
    physical_size_m: float = Field(
        ..., gt=0,
        description="Side length of the printed marker in metres",
    )


class MarkerUpdate(BaseModel):
    """Update marker fields (all optional)."""

    bim_element_guid: str | None = None
    bim_point_description: str | None = None
    world_x: float | None = None
    world_y: float | None = None
    world_z: float | None = None
    normal_x: float | None = None
    normal_y: float | None = None
    normal_z: float | None = None
    physical_size_m: float | None = None


class MarkerResponse(BaseModel):
    """Fiducial marker detail response."""

    id: uuid.UUID
    project_id: uuid.UUID
    marker_dict_id: int
    aruco_dict_type: str
    bim_model_id: uuid.UUID | None
    bim_element_guid: str | None
    bim_point_description: str | None
    world_x: float
    world_y: float
    world_z: float
    normal_x: float
    normal_y: float
    normal_z: float
    physical_size_m: float
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MarkerListResponse(BaseModel):
    """List of fiducial markers for a project."""

    markers: list[MarkerResponse]
    total: int


# ── Calibration Schemas ──────────────────────────────────────────────

class CalibrateRequest(BaseModel):
    """Request to calibrate a camera using a fiducial marker."""

    fov_horizontal_deg: float | None = Field(
        default=None,
        description="Horizontal FOV in degrees; used to compute fx if not already set",
    )
    image_width: int | None = Field(
        default=None, description="Override frame width (auto-detected from RTSP if None)",
    )
    image_height: int | None = Field(
        default=None, description="Override frame height (auto-detected from RTSP if None)",
    )


class CalibrationResult(BaseModel):
    """Result of a camera calibration attempt."""

    success: bool
    calibration_status: str
    marker_id: int | None = Field(
        default=None, description="ArUco marker ID that was detected",
    )
    marker_registry_id: uuid.UUID | None = Field(
        default=None, description="Database ID of the matched marker registry entry",
    )
    reprojection_error_px: float | None = Field(
        default=None, description="Mean reprojection error in pixels",
    )
    camera_position: dict | None = Field(
        default=None, description="Camera position in BIM world coords {x, y, z}",
    )
    candidate_element_count: int | None = Field(
        default=None, description="Number of BIM elements in the camera's view frustum",
    )
    message: str = ""


# ── Auto-Mapping Schemas ─────────────────────────────────────────────

class MappingResultItem(BaseModel):
    """Result of mapping a single detection to a BIM element."""

    defect_class: str
    confidence: float
    severity: str
    mapped_element_guid: str | None = None
    hit_position: dict | None = None  # {x, y, z}
    hit_distance_m: float | None = None
    was_deduplicated: bool = False
    defect_id: str | None = None


class AutoMappingResult(BaseModel):
    """Aggregate result of automated defect-to-BIM mapping for a camera."""

    camera_id: str
    camera_name: str
    frames_analyzed: int
    total_detections: int
    mapped_count: int
    deduplicated_count: int
    unmapped_count: int
    results: list[MappingResultItem]
    status: str = "completed"
