"""Defect request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel
from typing import Literal


class DefectResponse(BaseModel):
    """Full defect detail response."""

    id: uuid.UUID
    project_id: uuid.UUID
    inspection_id: uuid.UUID | None
    bim_model_id: uuid.UUID | None = None
    bim_element_guid: str | None
    defect_class: str
    severity: str
    severity_score: float
    confidence: float
    bbox: dict
    source_image_url: str
    annotated_image_url: str | None
    world_position: dict | None
    dimensions: dict | None
    status: str
    assigned_to_id: uuid.UUID | None
    notes: str | None
    remediation_recommendation: str | None
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DefectUpdate(BaseModel):
    """Update defect fields (all optional)."""

    status: Literal["detected", "confirmed", "assigned", "in_progress", "resolved", "verified"] | None = None
    assigned_to_id: uuid.UUID | None = None
    notes: str | None = None
    severity: Literal["low", "medium", "high", "critical"] | None = None
    bim_model_id: uuid.UUID | None = None
    bim_element_guid: str | None = None
    world_position: dict | None = None


class DefectListResponse(BaseModel):
    """Paginated defect list with severity summary."""

    defects: list[DefectResponse]
    total: int
    severity_summary: dict  # {"low": 5, "medium": 3, "high": 2, "critical": 1}
