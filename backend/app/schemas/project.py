"""Project request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """Create a new project."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    address: str | None = None
    client_name: str | None = None


class ProjectUpdate(BaseModel):
    """Update an existing project (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    address: str | None = None
    client_name: str | None = None
    status: str | None = None


class ProjectResponse(BaseModel):
    """Project detail response."""

    id: uuid.UUID
    name: str
    description: str | None
    address: str | None
    client_name: str | None
    organization_id: uuid.UUID
    created_by_id: uuid.UUID
    status: str
    defect_count: int = 0
    bim_model_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""

    projects: list[ProjectResponse]
    total: int
