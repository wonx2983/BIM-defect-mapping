"""Camera management endpoints — CRUD, BIM linking, auto-detection scheduling.

Endpoints:
    GET    /api/v1/cameras/              — List cameras for a project
    POST   /api/v1/cameras/              — Register a new camera
    GET    /api/v1/cameras/{id}          — Get camera details
    PUT    /api/v1/cameras/{id}          — Update camera
    DELETE /api/v1/cameras/{id}          — Delete camera
    POST   /api/v1/cameras/{id}/detect   — Run detection on camera feed, auto-map to BIM
    GET    /api/v1/cameras/schedule/status — Get auto-detection schedule status
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.exceptions import NotFoundError, ForbiddenError
from app.db.session import get_db
from app.models.camera import Camera, CameraStatus
from app.models.defect import Defect, DefectClass, DefectStatus, SeverityLevel
from app.models.project import Project
from app.models.user import User
from app.schemas.bim import CameraCreate, CameraListResponse, CameraResponse, CameraUpdate
from app.services.ml_service import get_detector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cameras", tags=["Cameras"])


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


@router.get("/", response_model=CameraListResponse)
async def list_cameras(
    project_id: uuid.UUID = Query(..., description="Project ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """List all cameras registered to a project."""
    await _verify_project_access(project_id, user, db)

    result = await db.execute(
        select(Camera)
        .where(Camera.project_id == project_id)
        .order_by(Camera.created_at.desc())
    )
    cameras = result.scalars().all()
    return CameraListResponse(
        cameras=[CameraResponse.model_validate(c) for c in cameras],
        total=len(cameras),
    )


@router.post("/", response_model=CameraResponse)
async def create_camera(
    body: CameraCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Register a new CCTV camera and link it to a BIM element."""
    await _verify_project_access(body.project_id, user, db)

    camera = Camera(
        project_id=body.project_id,
        name=body.name,
        rtsp_url=body.rtsp_url,
        bim_model_id=body.bim_model_id,
        bim_element_guid=body.bim_element_guid,
        bim_zone_label=body.bim_zone_label,
        world_position=body.world_position,
        location_description=body.location_description,
        frame_skip=body.frame_skip,
        auto_detect_enabled=body.auto_detect_enabled,
        auto_detect_interval_minutes=body.auto_detect_interval_minutes,
        created_by_id=user.id,
    )
    db.add(camera)
    await db.flush()
    return CameraResponse.model_validate(camera)


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Get camera details."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise NotFoundError("Camera not found")
    return CameraResponse.model_validate(camera)


@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: uuid.UUID,
    body: CameraUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Update camera fields — name, RTSP URL, BIM link, scheduling."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise NotFoundError("Camera not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(camera, field, value)

    await db.flush()
    return CameraResponse.model_validate(camera)


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Delete a camera."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise NotFoundError("Camera not found")
    await db.delete(camera)
    await db.flush()


@router.post("/{camera_id}/detect")
async def run_camera_detection(
    camera_id: uuid.UUID,
    max_frames: int = Query(default=50, description="Max frames to analyze"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Run defect detection on a camera's RTSP feed and auto-map results to BIM.

    This connects to the camera's RTSP stream, runs YOLOv11 on sampled frames,
    and automatically sets bim_element_guid and world_position on each detected
    defect from the camera's registered BIM link.
    """
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise NotFoundError("Camera not found")

    detector = get_detector()

    from ml.inference.video_processor import (
        process_rtsp_frames,
        FrameDetection,
        _deduplicate_detections,
        _iou,
    )

    loop = asyncio.get_event_loop()

    def _process():
        frame_detections = []
        try:
            for frame_idx, inference, annotated in process_rtsp_frames(
                rtsp_url=camera.rtsp_url,
                detector=detector,
                frame_skip=camera.frame_skip,
                max_frames=max_frames,
            ):
                fd = FrameDetection(
                    frame_index=frame_idx,
                    timestamp_ms=0,
                    detections=inference.detections,
                    inference_time_ms=inference.inference_time_ms,
                )
                frame_detections.append(fd)
        except Exception as e:
            logger.error(f"Camera {camera.name} RTSP error: {e}")
        return frame_detections

    frame_detections = await loop.run_in_executor(None, _process)

    # Deduplicate and save defects with BIM auto-mapping
    saved_defects = []
    seen: list[tuple[str, dict]] = []

    for fd in frame_detections:
        for det in fd.detections:
            is_dup = False
            for sc, sb in seen:
                if det.defect_class == sc and _iou(det.bbox_pixels, sb) > 0.5:
                    is_dup = True
                    break
            if not is_dup:
                seen.append((det.defect_class, det.bbox_pixels))
                try:
                    defect = Defect(
                        project_id=camera.project_id,
                        defect_class=DefectClass(det.defect_class),
                        severity=SeverityLevel(det.severity),
                        severity_score=det.severity_score,
                        confidence=det.confidence,
                        bbox=det.bbox,
                        source_image_url=f"camera://{camera.name}",
                        status=DefectStatus.DETECTED,
                        created_by_id=user.id,
                        notes=f"Auto-detected from camera '{camera.name}' at frame {fd.frame_index}",
                        # ── BIM AUTO-MAPPING ──
                        bim_element_guid=camera.bim_element_guid,
                        world_position=camera.world_position,
                    )
                    db.add(defect)
                    saved_defects.append({
                        "defect_class": det.defect_class,
                        "severity": det.severity,
                        "confidence": round(det.confidence, 4),
                        "bim_element_guid": camera.bim_element_guid,
                        "bim_zone": camera.bim_zone_label,
                    })
                except Exception as e:
                    logger.warning(f"Failed to save camera defect: {e}")

    # Update camera stats
    camera.last_detection_at = datetime.now(timezone.utc)
    camera.total_defects_found = (camera.total_defects_found or 0) + len(saved_defects)
    camera.status = CameraStatus.ACTIVE

    if saved_defects:
        await db.commit()
    else:
        await db.flush()

    total_detections = sum(len(fd.detections) for fd in frame_detections)

    return {
        "camera_id": str(camera.id),
        "camera_name": camera.name,
        "frames_analyzed": len(frame_detections),
        "total_detections": total_detections,
        "unique_defects_saved": len(saved_defects),
        "bim_element_guid": camera.bim_element_guid,
        "bim_zone": camera.bim_zone_label,
        "defects": saved_defects,
        "status": "completed",
    }
