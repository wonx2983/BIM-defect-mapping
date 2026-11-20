from app.services.uploads import stream_upload, upload_url
from app.services.runtime import run_blocking
from app.services.access import project_access, model_access, assignee_access, invalidate_calibration
"""BIM model management endpoints — upload IFC files, list models, get mapped defects.

Endpoints:
    POST /api/v1/bim/upload                    — Upload .ifc file
    GET  /api/v1/bim/{project_id}/models       — List BIM models for a project
    GET  /api/v1/bim/{model_id}                — Get model details
    DELETE /api/v1/bim/{model_id}              — Delete a BIM model
    GET  /api/v1/bim/{project_id}/defects-mapped — Get defects with BIM mappings
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import get_db
from app.models.bim_model import BIMModel, ProcessingStatus
from app.models.defect import Defect
from app.models.project import Project
from app.models.user import User
from app.schemas.bim import BIMModelListResponse, BIMModelResponse
from app.schemas.defect import DefectResponse

router = APIRouter(prefix="/api/v1/bim", tags=["BIM"])

ALLOWED_IFC_EXTENSIONS = {".ifc"}


@router.post("/upload", response_model=BIMModelResponse)
async def upload_bim_model(
    file: UploadFile = File(..., description="IFC model file (.ifc)"),
    project_id: str = Form(..., description="Project UUID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Upload an IFC file and create a BIM model record."""
    # Validate extension
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_IFC_EXTENSIONS:
            raise ValidationError(
                f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_IFC_EXTENSIONS)}"
            )

    # Verify project access
    proj_id = uuid.UUID(project_id)
    result = await db.execute(select(Project).where(Project.id == proj_id))
    project = result.scalar_one_or_none()
    if not project:
        raise NotFoundError("Project not found")
    if project.organization_id != user.organization_id:
        from app.core.exceptions import ForbiddenError
        raise ForbiddenError("Access denied to this project")

    file_path, file_size = await stream_upload(file, proj_id, "bim", 100 * 1024 * 1024, ALLOWED_IFC_EXTENSIONS)
    try:
        from ml.calibration.ifc_geometry import extract_meshes_from_ifc
        meshes = await run_blocking(extract_meshes_from_ifc, file_path)
        if not meshes:
            raise ValidationError("IFC contains no supported element geometry")
    except Exception:
        file_path.unlink(missing_ok=True)
        raise
    file_url = upload_url(file_path)

    # Create DB record
    bim_model = BIMModel(
        project_id=proj_id,
        original_filename=file.filename or "model.ifc",
        file_url=file_url,
        file_size_bytes=file_size,
        element_count=len(meshes),
        processing_status=ProcessingStatus.READY,
        uploaded_by_id=user.id,
    )
    db.add(bim_model)
    await db.flush()

    return BIMModelResponse.model_validate(bim_model)


@router.get("/{project_id}/models", response_model=BIMModelListResponse)
async def list_bim_models(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """List all BIM models for a project."""
    result = await db.execute(
        select(BIMModel)
        .where(BIMModel.project_id == project_id)
        .order_by(BIMModel.created_at.desc())
    )
    await project_access(project_id, user, db)
    models = result.scalars().all()
    return BIMModelListResponse(
        models=[BIMModelResponse.model_validate(m) for m in models],
        total=len(models),
    )


@router.get("/model/{model_id}", response_model=BIMModelResponse)
async def get_bim_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Get a single BIM model by ID."""
    result = await db.execute(select(BIMModel).where(BIMModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise NotFoundError("BIM model not found")
    await project_access(model.project_id, user, db)
    return BIMModelResponse.model_validate(model)


@router.delete("/model/{model_id}", status_code=204)
async def delete_bim_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Delete a BIM model."""
    result = await db.execute(select(BIMModel).where(BIMModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise NotFoundError("BIM model not found")
    await project_access(model.project_id, user, db)
    from app.models.camera import Camera
    from app.models.fiducial_marker import FiducialMarker
    from sqlalchemy import update
    for camera in (await db.scalars(select(Camera).where(Camera.bim_model_id == model_id))).all():
        invalidate_calibration(camera)
        camera.bim_model_id = None
    await db.execute(update(FiducialMarker).where(FiducialMarker.bim_model_id == model_id).values(bim_model_id=None))
    await db.execute(update(Defect).where(Defect.bim_model_id == model_id).values(bim_model_id=None, bim_element_guid=None, world_position=None))
    await db.delete(model)
    await db.flush()


@router.get("/{project_id}/defects-mapped")
async def get_mapped_defects(
    project_id: uuid.UUID,
    model_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Get defects scoped to a selected BIM version."""
    await project_access(project_id, user, db)
    await model_access(model_id, project_id, db)
    result = await db.execute(
        select(Defect)
        .where(
            Defect.project_id == project_id,
            Defect.bim_element_guid.isnot(None),
            Defect.bim_model_id == model_id,
        )
        .order_by(Defect.created_at.desc())
    )
    await project_access(project_id, user, db)
    defects = result.scalars().all()

    # Also get unmapped defects for the sidebar
    unmapped_result = await db.execute(
        select(Defect)
        .where(
            Defect.project_id == project_id,
            Defect.bim_element_guid.is_(None),
        )
        .order_by(Defect.created_at.desc())
    )
    unmapped = unmapped_result.scalars().all()

    return {
        "mapped": [DefectResponse.model_validate(d) for d in defects],
        "unmapped": [DefectResponse.model_validate(d) for d in unmapped],
        "mapped_count": len(defects),
        "unmapped_count": len(unmapped),
    }
