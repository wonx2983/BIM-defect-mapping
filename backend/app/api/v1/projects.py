"""Project management endpoints — CRUD with pagination and search."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.exceptions import ForbiddenError, NotFoundError
from app.db.session import get_db
from app.models.defect import Defect
from app.models.bim_model import BIMModel
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/v1/projects", tags=["Projects"])


async def _enrich_project(project: Project, db: AsyncSession) -> ProjectResponse:
    """Add computed fields (defect_count, bim_model_count) to a project response."""
    defect_count_result = await db.execute(
        select(func.count()).where(Defect.project_id == project.id)
    )
    bim_count_result = await db.execute(
        select(func.count()).where(BIMModel.project_id == project.id)
    )
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        address=project.address,
        client_name=project.client_name,
        organization_id=project.organization_id,
        created_by_id=project.created_by_id,
        status=project.status.value,
        defect_count=defect_count_result.scalar() or 0,
        bim_model_count=bim_count_result.scalar() or 0,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("/", response_model=ProjectListResponse)
async def list_projects(
    search: str | None = Query(None, description="Search by project name"),
    status: str | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """List all projects for the current user's organization."""
    query = select(Project).where(Project.organization_id == user.organization_id)

    if search:
        query = query.where(Project.name.ilike(f"%{search}%"))
    if status:
        query = query.where(Project.status == ProjectStatus(status))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Project.updated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    projects = result.scalars().all()

    enriched = [await _enrich_project(p, db) for p in projects]
    return ProjectListResponse(projects=enriched, total=total)


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Create a new project in the current user's organization."""
    project = Project(
        name=body.name,
        description=body.description,
        address=body.address,
        client_name=body.client_name,
        organization_id=user.organization_id,
        created_by_id=user.id,
    )
    db.add(project)
    await db.flush()
    return await _enrich_project(project, db)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Get a project by ID."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise NotFoundError("Project not found")
    if project.organization_id != user.organization_id:
        raise ForbiddenError("Access denied to this project")

    return await _enrich_project(project, db)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Update project details."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise NotFoundError("Project not found")
    if project.organization_id != user.organization_id:
        raise ForbiddenError("Access denied to this project")

    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"]:
        update_data["status"] = ProjectStatus(update_data["status"])

    for field, value in update_data.items():
        setattr(project, field, value)

    await db.flush()
    return await _enrich_project(project, db)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Archive a project (soft delete)."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise NotFoundError("Project not found")
    if project.organization_id != user.organization_id:
        raise ForbiddenError("Access denied to this project")

    project.status = ProjectStatus.ARCHIVED
    await db.flush()
