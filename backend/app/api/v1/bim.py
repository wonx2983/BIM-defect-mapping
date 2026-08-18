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

ALLOWED_IFC_EXTENSIONS = {".ifc", ".ifczip"}


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

    # Save file to disk
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[3]
    bim_dir = backend_root / settings.LOCAL_UPLOAD_DIR / "bim"
    bim_dir.mkdir(parents=True, exist_ok=True)

    file_bytes = await file.read()
    ext = Path(file.filename or "model.ifc").suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = bim_dir / unique_name
    file_path.write_bytes(file_bytes)

    file_url = f"/{settings.LOCAL_UPLOAD_DIR}/bim/{unique_name}"

    # Create DB record
    bim_model = BIMModel(
        project_id=proj_id,
        original_filename=file.filename or "model.ifc",
        file_url=file_url,
        file_size_bytes=len(file_bytes),
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
    await db.delete(model)
    await db.flush()


@router.get("/{project_id}/defects-mapped")
async def get_mapped_defects(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Get all defects that have BIM element mappings for 3D visualization."""
    result = await db.execute(
        select(Defect)
        .where(
            Defect.project_id == project_id,
            Defect.bim_element_guid.isnot(None),
        )
        .order_by(Defect.created_at.desc())
    )
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
