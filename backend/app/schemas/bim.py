"""BIM and Camera request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


# ── BIM Model Schemas ────────────────────────────────────────────────

class BIMModelResponse(BaseModel):
    """BIM model detail response."""
    id: uuid.UUID
    project_id: uuid.UUID
    original_filename: str
    file_url: str
    file_size_bytes: int
    processing_status: str
    element_count: int | None
    uploaded_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BIMModelListResponse(BaseModel):
    """List of BIM models for a project."""
    models: list[BIMModelResponse]
    total: int


# ── Camera Schemas ───────────────────────────────────────────────────

class CameraCreate(BaseModel):
    """Create a new camera."""
    name: str
    rtsp_url: str
    project_id: uuid.UUID
    bim_model_id: uuid.UUID | None = None
    bim_element_guid: str | None = None
    bim_zone_label: str | None = None
    world_position: dict | None = None
    location_description: str | None = None
    frame_skip: int = 15
    auto_detect_enabled: bool = False
    auto_detect_interval_minutes: int = 15


class CameraUpdate(BaseModel):
    """Update camera fields (all optional)."""
    name: str | None = None
    rtsp_url: str | None = None
    bim_model_id: uuid.UUID | None = None
    bim_element_guid: str | None = None
    bim_zone_label: str | None = None
    world_position: dict | None = None
    location_description: str | None = None
    frame_skip: int | None = None
    is_active: bool | None = None
    auto_detect_enabled: bool | None = None
    auto_detect_interval_minutes: int | None = None


class CameraResponse(BaseModel):
    """Camera detail response."""
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    rtsp_url: str
    bim_model_id: uuid.UUID | None
    bim_element_guid: str | None
    bim_zone_label: str | None
    world_position: dict | None
    location_description: str | None
    status: str
    is_active: bool
    frame_skip: int
    auto_detect_enabled: bool
    auto_detect_interval_minutes: int
    last_detection_at: datetime | None
    total_defects_found: int
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CameraListResponse(BaseModel):
    """List of cameras for a project."""
    cameras: list[CameraResponse]
    total: int
