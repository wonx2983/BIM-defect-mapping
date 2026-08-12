"""Detection API endpoints — upload images and detect construction defects.

Endpoints:
    POST /detect/image        — Upload single image → run inference → return results
    POST /detect/batch        — Upload multiple images → process and save defects
    GET  /detect/config       — Get current detection configuration
    PUT  /detect/config       — Update detection thresholds
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.defect import Defect, DefectClass, DefectStatus, SeverityLevel
from app.models.user import User
from app.schemas.detection import (
    BatchDetectionStatus,
    DetectionConfigResponse,
    DetectionConfigUpdate,
    DetectionResponse,
)
from app.services.ml_service import (
    get_detector,
    run_inference_and_annotate,
    save_uploaded_file,
)
from ml.inference.detector import CLASS_NAMES

router = APIRouter(prefix="/api/v1/detect", tags=["Detection"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _validate_image_file(file: UploadFile) -> None:
    """Validate uploaded file is an allowed image type."""
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            from app.core.exceptions import ValidationError
            raise ValidationError(
                f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )


@router.post("/image", response_model=DetectionResponse)
async def detect_single_image(
    file: UploadFile = File(..., description="Image file (JPEG, PNG)"),
    project_id: str = Form(..., description="Project UUID to associate defects with"),
    auto_save: bool = Form(default=True, description="Auto-save detected defects to project"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Upload a single image and detect construction defects.

    The image is processed through the YOLOv11 detection pipeline,
    then each detection is graded for severity. Results include
    bounding boxes, class labels, confidence scores, and severity grades.

    If auto_save is True, detected defects are automatically saved
    to the specified project's defect database.
    """
    _validate_image_file(file)

    # Read image bytes
    image_bytes = await file.read()
    if len(image_bytes) > MAX_FILE_SIZE:
        from app.core.exceptions import ValidationError
        raise ValidationError(f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB")

    # Save original image
    source_url = await save_uploaded_file(
        image_bytes, file.filename or "upload.jpg", subfolder="inspections"
    )

    # Run detection + annotation
    result, annotated_bytes = await run_inference_and_annotate(image_bytes)

    # Save annotated image
    annotated_url = await save_uploaded_file(
        annotated_bytes,
        f"annotated_{file.filename or 'result.jpg'}",
        subfolder="annotated",
    )

    # Auto-save defects to database
    if auto_save and result.detections:
        proj_uuid = uuid.UUID(project_id)
        for det in result.detections:
            defect = Defect(
                project_id=proj_uuid,
                defect_class=DefectClass(det.defect_class),
                severity=SeverityLevel(det.severity),
                severity_score=det.severity_score,
                confidence=det.confidence,
                bbox=det.bbox,
                source_image_url=source_url,
                annotated_image_url=annotated_url,
                dimensions=det.dimensions,
                status=DefectStatus.DETECTED,
                created_by_id=user.id,
            )
            db.add(defect)
        await db.flush()

    return DetectionResponse(
        detections=[d.__dict__ if hasattr(d, "__dict__") else d for d in result.to_dict()["detections"]],
        detection_count=result.detection_count,
        severity_summary=result.severity_summary,
        image_width=result.image_width,
        image_height=result.image_height,
        inference_time_ms=result.inference_time_ms,
        model_name=result.model_name,
        source_image_url=source_url,
        annotated_image_url=annotated_url,
    )


@router.post("/batch", response_model=BatchDetectionStatus)
async def detect_batch(
    files: list[UploadFile] = File(..., description="Multiple image files"),
    project_id: str = Form(..., description="Project UUID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Upload multiple images for batch defect detection.

    Each image is processed sequentially. All detected defects are
    automatically saved to the specified project.

    Returns a summary of all detections across all images.
    """
    total_defects = 0
    severity_summary = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    proj_uuid = uuid.UUID(project_id)

    for file in files:
        _validate_image_file(file)
        image_bytes = await file.read()

        if len(image_bytes) > MAX_FILE_SIZE:
            continue  # Skip oversized files

        source_url = await save_uploaded_file(
            image_bytes, file.filename or "upload.jpg", subfolder="inspections"
        )

        result, annotated_bytes = await run_inference_and_annotate(image_bytes)

        annotated_url = await save_uploaded_file(
            annotated_bytes,
            f"annotated_{file.filename or 'result.jpg'}",
            subfolder="annotated",
        )

        for det in result.detections:
            defect = Defect(
                project_id=proj_uuid,
                defect_class=DefectClass(det.defect_class),
                severity=SeverityLevel(det.severity),
                severity_score=det.severity_score,
                confidence=det.confidence,
                bbox=det.bbox,
                source_image_url=source_url,
                annotated_image_url=annotated_url,
                dimensions=det.dimensions,
                status=DefectStatus.DETECTED,
                created_by_id=user.id,
            )
            db.add(defect)

        total_defects += result.detection_count
        for sev, count in result.severity_summary.items():
            severity_summary[sev] += count

    await db.flush()

    return BatchDetectionStatus(
        task_id=uuid.uuid4().hex,
        status="completed",
        total_images=len(files),
        processed_images=len(files),
        total_defects=total_defects,
        severity_summary=severity_summary,
        progress_pct=100.0,
    )


@router.get("/config", response_model=DetectionConfigResponse)
async def get_detection_config(
    user: User = Depends(get_current_active_user),
):
    """Get the current detection model configuration."""
    settings = get_settings()
    return DetectionConfigResponse(
        confidence_threshold=settings.ML_CONFIDENCE_THRESHOLD,
        model_name=settings.ML_MODEL_PATH.split("/")[-1],
        device=settings.ML_DEVICE,
        supported_classes=list(CLASS_NAMES.values()),
        severity_levels=["low", "medium", "high", "critical"],
    )
