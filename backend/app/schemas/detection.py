"""Detection request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BBoxSchema(BaseModel):
    """Normalized bounding box coordinates (0-1)."""
    x: float
    y: float
    w: float
    h: float


class BBoxPixelsSchema(BaseModel):
    """Absolute pixel bounding box coordinates."""
    x1: int
    y1: int
    x2: int
    y2: int


class DimensionsSchema(BaseModel):
    """Defect dimensions in pixels."""
    width_px: int
    height_px: int
    area_px: int


class DetectionItemSchema(BaseModel):
    """Single defect detection result."""
    defect_class: str
    confidence: float
    severity: str
    severity_score: float
    bbox: BBoxSchema
    bbox_pixels: BBoxPixelsSchema
    dimensions: DimensionsSchema


class DetectionResponse(BaseModel):
    """Response from single-image detection."""
    model_config = {"protected_namespaces": ()}

    detections: list[DetectionItemSchema]
    detection_count: int
    severity_summary: dict  # {"low": 5, "medium": 3, ...}
    image_width: int
    image_height: int
    inference_time_ms: float
    model_name: str
    source_image_url: str
    annotated_image_url: str | None = None


class BatchDetectionRequest(BaseModel):
    """Request to process multiple images."""
    project_id: uuid.UUID
    inspection_id: uuid.UUID | None = None
    auto_save: bool = Field(
        default=True,
        description="Automatically save detected defects to the project",
    )


class BatchDetectionStatus(BaseModel):
    """Status of a batch detection job."""
    task_id: str
    status: str  # queued, processing, completed, failed
    total_images: int
    processed_images: int
    total_defects: int
    severity_summary: dict
    progress_pct: float
    started_at: datetime | None = None
    completed_at: datetime | None = None


class DetectionConfigResponse(BaseModel):
    """Current detection configuration."""
    model_config = {"protected_namespaces": ()}

    confidence_threshold: float
    model_name: str
    device: str
    supported_classes: list[str]
    severity_levels: list[str]


class DetectionConfigUpdate(BaseModel):
    """Update detection configuration."""
    confidence_threshold: float | None = Field(None, ge=0.05, le=0.95)
