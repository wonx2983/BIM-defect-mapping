from app.services.inspections import record_inspection
from app.services.runtime import run_blocking
from app.services.access import project_access, model_access, assignee_access, invalidate_calibration
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


@router.get("/monitoring/status")
async def monitoring_status(db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_active_user)):
    from datetime import timedelta
    from app.models.monitoring_worker import MonitoringWorker
    count = await db.scalar(select(func.count()).select_from(MonitoringWorker).where(
        MonitoringWorker.last_seen > datetime.now(timezone.utc) - timedelta(seconds=45)))
    return {"available": bool(count), "active_workers": count}


@router.get("/{camera_id}/preview")
async def preview_camera(camera_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_active_user)):
    import cv2
    from fastapi.responses import Response
    from ml.calibration.marker_detector import grab_frame_from_rtsp, detect_markers
    from app.models.fiducial_marker import FiducialMarker
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise NotFoundError("Camera not found")
    await project_access(camera.project_id, user, db)
    markers = (await db.scalars(select(FiducialMarker).where(
        FiducialMarker.project_id == camera.project_id,
        FiducialMarker.bim_model_id == camera.bim_model_id))).all()
    patterns = {(marker.aruco_dict_type, marker.marker_dict_id) for marker in markers}
    source = camera.rtsp_url
    def capture_preview():
        frame = grab_frame_from_rtsp(source)
        for dictionary in sorted({pattern[0] for pattern in patterns} or {"DICT_4X4_50"}):
            for found in detect_markers(frame, dictionary):
                registered = (dictionary, found.marker_id) in patterns
                colour = (0, 180, 0) if registered else (0, 120, 255)
                cv2.polylines(frame, [found.corners.astype('int32')], True, colour, 2)
                point = tuple(found.corners[0].astype(int))
                label = f"{dictionary} ID {found.marker_id}: {'registered' if registered else 'unregistered'}"
                cv2.putText(frame, label, point, cv2.FONT_HERSHEY_SIMPLEX, .6, colour, 2)
        return cv2.imencode(".jpg", frame)
    success, encoded = await run_blocking(capture_preview)
    if not success:
        from app.core.exceptions import ValidationError
        raise ValidationError("Unable to encode camera preview")
    return Response(encoded.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/{camera_id}/start-monitoring", response_model=CameraResponse)
async def start_monitoring(camera_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_active_user)):
    from app.api.v1.calibration import calibrate_camera
    from app.schemas.calibration import CalibrateRequest
    from app.core.exceptions import AppException, ValidationError
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise NotFoundError("Camera not found")
    await project_access(camera.project_id, user, db)
    if not camera.bim_model_id or not camera.fov_horizontal_deg:
        raise ValidationError("Select a BIM model and supply the camera's horizontal field of view")
    worker = await monitoring_status(db, user)
    if not worker["available"]:
        raise AppException("Monitoring worker is offline. Start the camera worker and retry.", "WORKER_OFFLINE", 503)
    result = await calibrate_camera(camera_id, CalibrateRequest(fov_horizontal_deg=camera.fov_horizontal_deg), db, user)
    if not result.success:
        raise ValidationError(result.message)
    camera.auto_detect_enabled = True
    camera.is_active = True
    camera.last_attempt_at = None
    await db.flush()
    await db.refresh(camera)
    return CameraResponse.model_validate(camera)


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


@router.get("", response_model=CameraListResponse, include_in_schema=False)
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


@router.post("", response_model=CameraResponse, include_in_schema=False)
@router.post("/", response_model=CameraResponse)
async def create_camera(
    body: CameraCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Register a new CCTV camera and link it to a BIM element."""
    await _verify_project_access(body.project_id, user, db)

    if body.auto_detect_enabled:
        from app.core.exceptions import ValidationError
        raise ValidationError("Calibrate a new camera before enabling scheduling")
    await model_access(body.bim_model_id, body.project_id, db)
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
        fov_horizontal_deg=body.fov_horizontal_deg,
        image_width=body.image_width,
        image_height=body.image_height,
        auto_detect_enabled=body.auto_detect_enabled,
        auto_detect_interval_minutes=body.auto_detect_interval_minutes,
        created_by_id=user.id,
    )
    db.add(camera)
    await db.flush()
    await db.refresh(camera)
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
    await project_access(camera.project_id, user, db)
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
    await project_access(camera.project_id, user, db)

    if body.auto_detect_enabled and camera.calibration_status != "calibrated":
        from app.core.exceptions import ValidationError
        raise ValidationError("Scheduled detection requires a calibrated camera")
    update_data = body.model_dump(exclude_unset=True)
    required = {"name", "rtsp_url", "frame_skip", "is_active", "auto_detect_enabled", "auto_detect_interval_minutes"}
    if any(update_data.get(key) is None for key in required & update_data.keys()):
        from app.core.exceptions import ValidationError
        raise ValidationError("Required camera fields cannot be null")
    if "bim_model_id" in update_data:
        await model_access(body.bim_model_id, camera.project_id, db)
    if {"rtsp_url", "bim_model_id", "fov_horizontal_deg", "image_width", "image_height"} & update_data.keys():
        invalidate_calibration(camera)
        camera.intrinsics = None
        update_data["auto_detect_enabled"] = False
    for field, value in update_data.items():
        setattr(camera, field, value)

    await db.flush()
    await db.refresh(camera)
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
    await project_access(camera.project_id, user, db)
    await db.delete(camera)
    await db.flush()


@router.post("/{camera_id}/detect")
async def run_camera_detection(
    camera_id: uuid.UUID,
    max_frames: int = Query(default=50, ge=1, le=300, description="Max frames to analyze"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Run defect detection on a camera's RTSP feed and auto-map results to BIM.

    Behavior depends on calibration status:
      - **Calibrated**: Routes to the Phase 2 auto-mapping pipeline which uses
        PnP pose + raycasting for per-pixel BIM element mapping.
      - **Uncalibrated**: Falls back to Phase 1 zone-based mapping which assigns
        all detections to the camera's single bim_element_guid.
    """
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise NotFoundError("Camera not found")
    await project_access(camera.project_id, user, db)

    # ── Phase 2: Calibrated → auto-mapping via raycasting ────────────
    if (
        camera.calibration_status == "calibrated"
        and camera.pose_rotation is not None
        and camera.pose_translation is not None
        and camera.intrinsics is not None
    ):
        from app.api.v1.calibration import run_auto_mapped_detection
        return await run_auto_mapped_detection(camera_id, max_frames, db, user)

    # Uncalibrated detections are observations, never invented world positions.
    from app.services.camera_capture import capture_observations
    try:
        frames = await run_blocking(capture_observations, camera, get_detector(), max_frames)
    except Exception:
        camera.status = CameraStatus.ERROR
        await db.commit()
        raise
    inspection_id = record_inspection(db, camera.project_id, user.id, "Camera observations")
    saved = []
    for frame in frames:
        for det in frame.detections:
            defect = Defect(id=uuid.uuid4(), project_id=camera.project_id, inspection_id=inspection_id,
                defect_class=DefectClass(det.defect_class), severity=SeverityLevel(det.severity),
                severity_score=det.severity_score, confidence=det.confidence, bbox=det.bbox,
                source_image_url=frame.snapshot_url, status=DefectStatus.DETECTED,
                created_by_id=user.id,
                notes=f"Camera {camera.name}: uncalibrated observation; physical identity unverified")
            db.add(defect)
            saved.append({"defect_class": det.defect_class, "severity": det.severity,
                          "confidence": det.confidence, "bim_element_guid": None, "bim_zone": None})
    camera.status = CameraStatus.ACTIVE
    camera.last_detection_at = datetime.now(timezone.utc)
    camera.total_defects_found += len(saved)
    await db.commit()
    return {"camera_id": str(camera.id), "camera_name": camera.name,
            "frames_analyzed": len(frames), "total_detections": len(saved),
            "unique_defects_saved": len(saved), "mapped_count": 0,
            "counting_mode": "observations", "bim_element_guid": None, "bim_zone": None,
            "defects": saved, "status": "completed"}
