"""Fiducial marker registry endpoints — CRUD for ArUco markers at known BIM coordinates.

Endpoints:
    GET    /api/v1/markers/              — List markers for a project
    POST   /api/v1/markers/              — Register a new marker
    GET    /api/v1/markers/{id}          — Get marker details
    PUT    /api/v1/markers/{id}          — Update marker
    DELETE /api/v1/markers/{id}          — Delete marker
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.exceptions import NotFoundError, ForbiddenError
from app.db.session import get_db
from app.models.fiducial_marker import FiducialMarker
from app.models.project import Project
from app.models.user import User
from app.schemas.calibration import MarkerCreate, MarkerListResponse, MarkerResponse, MarkerUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/markers", tags=["Fiducial Markers"])


async def _verify_project_access(
    project_id: uuid.UUID, user: User, db: AsyncSession,
) -> None:
    """Verify the user's organization owns the project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFoundError("Project not found")
    if project.organization_id != user.organization_id:
        raise ForbiddenError("Access denied to this project")


@router.get("/", response_model=MarkerListResponse)
async def list_markers(
    project_id: uuid.UUID = Query(..., description="Project ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """List all fiducial markers registered to a project."""
    await _verify_project_access(project_id, user, db)

    result = await db.execute(
        select(FiducialMarker)
        .where(FiducialMarker.project_id == project_id)
        .order_by(FiducialMarker.created_at.desc())
    )
    markers = result.scalars().all()
    return MarkerListResponse(
        markers=[MarkerResponse.model_validate(m) for m in markers],
        total=len(markers),
    )


@router.post("/", response_model=MarkerResponse, status_code=201)
async def create_marker(
    body: MarkerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Register a new fiducial marker at a known BIM coordinate.

    The marker must be physically placed at the specified coordinate on the
    real structure.  This step is done once per marker, not per camera.
    """
    await _verify_project_access(body.project_id, user, db)

    # Check for duplicate marker_dict_id within the same project
    existing = await db.execute(
        select(FiducialMarker).where(
            FiducialMarker.project_id == body.project_id,
            FiducialMarker.marker_dict_id == body.marker_dict_id,
            FiducialMarker.aruco_dict_type == body.aruco_dict_type,
        )
    )
    if existing.scalar_one_or_none():
        from app.core.exceptions import ValidationError
        raise ValidationError(
            f"Marker ID {body.marker_dict_id} ({body.aruco_dict_type}) "
            f"is already registered in this project"
        )

    marker = FiducialMarker(
        project_id=body.project_id,
        marker_dict_id=body.marker_dict_id,
        aruco_dict_type=body.aruco_dict_type,
        bim_model_id=body.bim_model_id,
        bim_element_guid=body.bim_element_guid,
        bim_point_description=body.bim_point_description,
        world_x=body.world_x,
        world_y=body.world_y,
        world_z=body.world_z,
        normal_x=body.normal_x,
        normal_y=body.normal_y,
        normal_z=body.normal_z,
        physical_size_m=body.physical_size_m,
        created_by_id=user.id,
    )
    db.add(marker)
    await db.flush()
    await db.refresh(marker)

    logger.info(
        "Marker %d registered at (%.2f, %.2f, %.2f) in project %s",
        body.marker_dict_id, body.world_x, body.world_y, body.world_z,
        body.project_id,
    )
    return MarkerResponse.model_validate(marker)


@router.get("/{marker_id}", response_model=MarkerResponse)
async def get_marker(
    marker_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Get a single marker by ID."""
    result = await db.execute(
        select(FiducialMarker).where(FiducialMarker.id == marker_id)
    )
    marker = result.scalar_one_or_none()
    if not marker:
        raise NotFoundError("Fiducial marker not found")

    await _verify_project_access(marker.project_id, user, db)
    return MarkerResponse.model_validate(marker)


@router.put("/{marker_id}", response_model=MarkerResponse)
async def update_marker(
    marker_id: uuid.UUID,
    body: MarkerUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Update marker fields — position, description, size."""
    result = await db.execute(
        select(FiducialMarker).where(FiducialMarker.id == marker_id)
    )
    marker = result.scalar_one_or_none()
    if not marker:
        raise NotFoundError("Fiducial marker not found")

    await _verify_project_access(marker.project_id, user, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(marker, field, value)

    await db.flush()
    await db.refresh(marker)
    return MarkerResponse.model_validate(marker)


@router.delete("/{marker_id}", status_code=204)
async def delete_marker(
    marker_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Delete a fiducial marker."""
    result = await db.execute(
        select(FiducialMarker).where(FiducialMarker.id == marker_id)
    )
    marker = result.scalar_one_or_none()
    if not marker:
        raise NotFoundError("Fiducial marker not found")

    await _verify_project_access(marker.project_id, user, db)
    await db.delete(marker)
    await db.flush()
