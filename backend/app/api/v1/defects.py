"""Defect management endpoints — CRUD, filtering, and status updates.

Endpoints:
    GET    /defects/              — List defects with filters (project, severity, class, status)
    GET    /defects/{id}          — Get single defect detail
    PUT    /defects/{id}          — Update defect (status, assignment, notes, BIM mapping)
    DELETE /defects/{id}          — Delete a defect
    GET    /defects/stats         — Aggregated defect statistics for a project
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.exceptions import ForbiddenError, NotFoundError
from app.db.session import get_db
from app.models.defect import Defect, DefectClass, DefectStatus, SeverityLevel
from app.models.project import Project
from app.models.user import User
from app.schemas.defect import DefectListResponse, DefectResponse, DefectUpdate

router = APIRouter(prefix="/api/v1/defects", tags=["Defects"])


async def _verify_project_access(
    project_id: uuid.UUID, user: User, db: AsyncSession
) -> None:
    """Verify the user's organization owns the project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFoundError("Project not found")
    if project.organization_id != user.organization_id:
        raise ForbiddenError("Access denied to this project")


@router.get("/", response_model=DefectListResponse)
async def list_defects(
    project_id: uuid.UUID = Query(..., description="Project ID (required)"),
    severity: str | None = Query(None, description="Filter by severity level"),
    defect_class: str | None = Query(None, description="Filter by defect class"),
    status: str | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """List defects for a project with optional filters."""
    await _verify_project_access(project_id, user, db)

    query = select(Defect).where(Defect.project_id == project_id)

    if severity:
        query = query.where(Defect.severity == SeverityLevel(severity))
    if defect_class:
        query = query.where(Defect.defect_class == DefectClass(defect_class))
    if status:
        query = query.where(Defect.status == DefectStatus(status))

    # Count total matching
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Severity summary for this filtered set
    severity_query = (
        select(
            Defect.severity,
            func.count().label("count"),
        )
        .where(Defect.project_id == project_id)
        .group_by(Defect.severity)
    )
    severity_result = await db.execute(severity_query)
    severity_summary = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for row in severity_result:
        severity_summary[row.severity.value] = row.count

    # Paginate
    query = query.order_by(Defect.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    defects = result.scalars().all()

    return DefectListResponse(
        defects=[DefectResponse.model_validate(d) for d in defects],
        total=total,
        severity_summary=severity_summary,
    )


@router.get("/stats")
async def get_defect_stats(
    project_id: uuid.UUID = Query(..., description="Project ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Get aggregated defect statistics for a project.

    Returns counts by severity, class, status, and recent trends.
    """
    await _verify_project_access(project_id, user, db)

    # Total count
    total_result = await db.execute(
        select(func.count()).where(Defect.project_id == project_id)
    )
    total = total_result.scalar() or 0

    # By severity
    sev_result = await db.execute(
        select(Defect.severity, func.count().label("count"))
        .where(Defect.project_id == project_id)
        .group_by(Defect.severity)
    )
    by_severity = {row.severity.value: row.count for row in sev_result}

    # By class
    cls_result = await db.execute(
        select(Defect.defect_class, func.count().label("count"))
        .where(Defect.project_id == project_id)
        .group_by(Defect.defect_class)
    )
    by_class = {row.defect_class.value: row.count for row in cls_result}

    # By status
    status_result = await db.execute(
        select(Defect.status, func.count().label("count"))
        .where(Defect.project_id == project_id)
        .group_by(Defect.status)
    )
    by_status = {row.status.value: row.count for row in status_result}

    # Average confidence and severity score
    avg_result = await db.execute(
        select(
            func.avg(Defect.confidence).label("avg_confidence"),
            func.avg(Defect.severity_score).label("avg_severity_score"),
        ).where(Defect.project_id == project_id)
    )
    avg_row = avg_result.one()

    return {
        "total": total,
        "by_severity": by_severity,
        "by_class": by_class,
        "by_status": by_status,
        "avg_confidence": round(float(avg_row.avg_confidence or 0), 4),
        "avg_severity_score": round(float(avg_row.avg_severity_score or 0), 4),
    }


@router.get("/{defect_id}", response_model=DefectResponse)
async def get_defect(
    defect_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Get a single defect by ID."""
    result = await db.execute(select(Defect).where(Defect.id == defect_id))
    defect = result.scalar_one_or_none()
    if not defect:
        raise NotFoundError("Defect not found")

    await _verify_project_access(defect.project_id, user, db)
    return DefectResponse.model_validate(defect)


@router.put("/{defect_id}", response_model=DefectResponse)
async def update_defect(
    defect_id: uuid.UUID,
    body: DefectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Update defect fields — status, assignment, notes, severity override, BIM mapping."""
    result = await db.execute(select(Defect).where(Defect.id == defect_id))
    defect = result.scalar_one_or_none()
    if not defect:
        raise NotFoundError("Defect not found")

    await _verify_project_access(defect.project_id, user, db)

    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"]:
        update_data["status"] = DefectStatus(update_data["status"])
    if "severity" in update_data and update_data["severity"]:
        update_data["severity"] = SeverityLevel(update_data["severity"])

    for field, value in update_data.items():
        setattr(defect, field, value)

    await db.flush()
    return DefectResponse.model_validate(defect)


@router.delete("/{defect_id}", status_code=204)
async def delete_defect(
    defect_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Delete a defect permanently."""
    result = await db.execute(select(Defect).where(Defect.id == defect_id))
    defect = result.scalar_one_or_none()
    if not defect:
        raise NotFoundError("Defect not found")

    await _verify_project_access(defect.project_id, user, db)
    await db.delete(defect)
    await db.flush()
