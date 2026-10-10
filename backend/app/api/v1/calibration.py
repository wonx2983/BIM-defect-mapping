"""Camera calibration endpoints — PnP calibration and auto-mapping trigger.

Endpoints:
    POST /api/v1/calibration/{camera_id}/calibrate  — Run PnP calibration
    GET  /api/v1/calibration/{camera_id}/status      — Get calibration status
    POST /api/v1/calibration/{camera_id}/auto-detect  — Run detection with auto-mapping
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.exceptions import NotFoundError, ForbiddenError
from app.db.session import get_db
from app.models.bim_model import BIMModel
from app.models.camera import Camera
from app.models.defect import Defect, DefectClass, DefectStatus, SeverityLevel
from app.models.fiducial_marker import FiducialMarker
from app.models.project import Project
from app.models.user import User
from app.schemas.calibration import CalibrateRequest, CalibrationResult as CalibrationResultSchema
from app.schemas.calibration import AutoMappingResult, MappingResultItem
from app.services.ml_service import get_detector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calibration", tags=["Calibration"])


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


def _get_ifc_path(bim_model: BIMModel) -> Path | None:
    """Resolve the IFC file path on disk from a BIM model record."""
    if not bim_model or not bim_model.file_url:
        return None
    backend_root = Path(__file__).resolve().parents[3]
    # file_url is like "/uploads/bim/abc123.ifc"
    relative = bim_model.file_url.lstrip("/")
    full_path = backend_root / relative
    if full_path.exists():
        return full_path
    return None


@router.post("/{camera_id}/calibrate", response_model=CalibrationResultSchema)
async def calibrate_camera(
    camera_id: uuid.UUID,
    body: CalibrateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Run PnP calibration on a camera using fiducial markers.

    Grabs a frame from the camera's RTSP stream, detects ArUco markers,
    matches against the marker registry, solves PnP for the camera's pose,
    and computes the candidate element set.
    """
    # Load camera
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise NotFoundError("Camera not found")

    await _verify_project_access(camera.project_id, user, db)

    # Mark as calibrating
    camera.calibration_status = "calibrating"
    await db.flush()

    # Load marker registry for this project
    markers_result = await db.execute(
        select(FiducialMarker).where(FiducialMarker.project_id == camera.project_id)
    )
    markers = markers_result.scalars().all()

    if not markers:
        camera.calibration_status = "failed"
        await db.flush()
        return CalibrationResultSchema(
            success=False,
            calibration_status="failed",
            message="No fiducial markers registered for this project. "
                    "Register at least one marker before calibrating.",
        )

    marker_registry = [
        {
            "id": str(m.id),
            "marker_dict_id": m.marker_dict_id,
            "aruco_dict_type": m.aruco_dict_type,
            "world_x": m.world_x,
            "world_y": m.world_y,
            "world_z": m.world_z,
            "normal_x": m.normal_x,
            "normal_y": m.normal_y,
            "normal_z": m.normal_z,
            "physical_size_m": m.physical_size_m,
        }
        for m in markers
    ]

    # Resolve IFC path for candidate-set computation
    ifc_path: Path | None = None
    if camera.bim_model_id:
        bim_result = await db.execute(
            select(BIMModel).where(BIMModel.id == camera.bim_model_id)
        )
        bim_model = bim_result.scalar_one_or_none()
        if bim_model:
            ifc_path = _get_ifc_path(bim_model)

    # Determine FOV and image dimensions
    fov = body.fov_horizontal_deg or camera.fov_horizontal_deg
    img_w = body.image_width or camera.image_width
    img_h = body.image_height or camera.image_height

    # Run calibration in a thread (blocking OpenCV / RTSP operations)
    loop = asyncio.get_event_loop()

    def _run_calibration():
        from ml.calibration.camera_calibrator import calibrate_camera_from_rtsp
        from ml.calibration.pose_solver import CameraIntrinsics

        intrinsics = None
        if camera.intrinsics:
            intrinsics = CameraIntrinsics.from_dict(camera.intrinsics)

        return calibrate_camera_from_rtsp(
            rtsp_url=camera.rtsp_url,
            marker_registry=marker_registry,
            intrinsics=intrinsics,
            fov_horizontal_deg=fov,
            ifc_path=str(ifc_path) if ifc_path else None,
        )

    cal_result = await loop.run_in_executor(None, _run_calibration)

    # Persist results
    if cal_result.success and cal_result.pnp_result:
        pnp = cal_result.pnp_result

        camera.intrinsics = cal_result.intrinsics.to_dict() if cal_result.intrinsics else None
        camera.pose_rotation = {
            "matrix": pnp.rotation_matrix.flatten().tolist(),
            "rvec": pnp.rvec.tolist(),
        }
        camera.pose_translation = {
            "x": float(pnp.camera_position_world[0]),
            "y": float(pnp.camera_position_world[1]),
            "z": float(pnp.camera_position_world[2]),
        }
        camera.calibration_status = "calibrated"
        camera.calibration_error_px = pnp.reprojection_error
        camera.calibrated_at = datetime.now(timezone.utc)
        camera.image_width = cal_result.image_width
        camera.image_height = cal_result.image_height

        if fov:
            camera.fov_horizontal_deg = fov

        if cal_result.registry_marker_id:
            camera.calibrated_with_marker_id = uuid.UUID(cal_result.registry_marker_id)

        if cal_result.candidate_guids is not None:
            camera.candidate_element_guids = cal_result.candidate_guids

        # Also update world_position with the camera's computed position
        camera.world_position = {
            "x": float(pnp.camera_position_world[0]),
            "y": float(pnp.camera_position_world[1]),
            "z": float(pnp.camera_position_world[2]),
        }

        await db.commit()

        logger.info(
            "Camera '%s' calibrated successfully: error=%.2f px, "
            "%d candidate elements",
            camera.name, pnp.reprojection_error,
            len(cal_result.candidate_guids or []),
        )

        return CalibrationResultSchema(
            success=True,
            calibration_status="calibrated",
            marker_id=cal_result.detected_marker_id,
            marker_registry_id=(
                uuid.UUID(cal_result.registry_marker_id)
                if cal_result.registry_marker_id else None
            ),
            reprojection_error_px=pnp.reprojection_error,
            camera_position={
                "x": float(pnp.camera_position_world[0]),
                "y": float(pnp.camera_position_world[1]),
                "z": float(pnp.camera_position_world[2]),
            },
            candidate_element_count=len(cal_result.candidate_guids or []),
            message=f"Calibration successful. Reprojection error: "
                    f"{pnp.reprojection_error:.2f} px",
        )
    else:
        camera.calibration_status = "failed"
        await db.commit()

        return CalibrationResultSchema(
            success=False,
            calibration_status="failed",
            marker_id=cal_result.detected_marker_id,
            message=cal_result.error_message or "Calibration failed",
        )


@router.get("/{camera_id}/status")
async def get_calibration_status(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Get the current calibration status for a camera."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise NotFoundError("Camera not found")

    return {
        "camera_id": str(camera.id),
        "camera_name": camera.name,
        "calibration_status": camera.calibration_status,
        "calibration_error_px": camera.calibration_error_px,
        "calibrated_at": camera.calibrated_at.isoformat() if camera.calibrated_at else None,
        "calibrated_with_marker_id": (
            str(camera.calibrated_with_marker_id) if camera.calibrated_with_marker_id else None
        ),
        "has_intrinsics": camera.intrinsics is not None,
        "has_pose": camera.pose_rotation is not None and camera.pose_translation is not None,
        "candidate_element_count": (
            len(camera.candidate_element_guids) if camera.candidate_element_guids else 0
        ),
        "camera_position": camera.pose_translation,
    }


@router.post("/{camera_id}/auto-detect", response_model=AutoMappingResult)
async def run_auto_mapped_detection(
    camera_id: uuid.UUID,
    max_frames: int = Query(default=50, description="Max frames to analyze"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Run defect detection on a calibrated camera's RTSP feed with automatic BIM mapping.

    This is the full Phase 2 pipeline: detect defects → convert pixels to rays →
    raycast against BIM → de-duplicate → save.

    Requires the camera to be calibrated first (POST .../calibrate).
    Falls back to simple zone-based mapping if uncalibrated.
    """
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise NotFoundError("Camera not found")

    await _verify_project_access(camera.project_id, user, db)

    # Check calibration status
    is_calibrated = (
        camera.calibration_status == "calibrated"
        and camera.pose_rotation is not None
        and camera.pose_translation is not None
        and camera.intrinsics is not None
    )

    if not is_calibrated:
        # Fall back to the existing simple detection (Phase 1 behavior)
        from app.api.v1.cameras import run_camera_detection
        return await run_camera_detection(camera_id, max_frames, db, user)

    # ── Phase 2: Calibrated auto-mapping ──────────────────────────────

    detector = get_detector()
    loop = asyncio.get_event_loop()

    # Step 1: Run YOLO detection on RTSP frames
    def _detect():
        from ml.inference.video_processor import process_rtsp_frames, FrameDetection
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

    frame_detections = await loop.run_in_executor(None, _detect)

    # Step 2: Load BIM geometry for raycasting
    candidate_meshes: dict = {}
    if camera.bim_model_id and camera.candidate_element_guids:
        try:
            bim_result = await db.execute(
                select(BIMModel).where(BIMModel.id == camera.bim_model_id)
            )
            bim_model = bim_result.scalar_one_or_none()
            ifc_path = _get_ifc_path(bim_model) if bim_model else None

            if ifc_path:
                def _load_meshes():
                    from ml.calibration.ifc_geometry import extract_meshes_from_ifc
                    all_meshes = extract_meshes_from_ifc(str(ifc_path))
                    # Filter to candidate set only
                    guids = set(camera.candidate_element_guids)
                    return {g: m for g, m in all_meshes.items() if g in guids}

                candidate_meshes = await loop.run_in_executor(None, _load_meshes)
        except Exception as e:
            logger.warning("Failed to load BIM meshes for auto-mapping: %s", e)

    # Step 3: Reconstruct camera pose from stored data
    from ml.calibration.pose_solver import CameraIntrinsics
    intrinsics = CameraIntrinsics.from_dict(camera.intrinsics)
    R = np.array(camera.pose_rotation["matrix"]).reshape(3, 3)
    cam_pos = np.array([
        camera.pose_translation["x"],
        camera.pose_translation["y"],
        camera.pose_translation["z"],
    ])

    # Step 4: Load existing defects for de-duplication
    existing_defects_result = await db.execute(
        select(Defect).where(
            Defect.project_id == camera.project_id,
            Defect.bim_element_guid.isnot(None),
        )
    )
    existing_defects = [
        {
            "id": str(d.id),
            "bim_element_guid": d.bim_element_guid,
            "defect_class": d.defect_class.value if hasattr(d.defect_class, "value") else d.defect_class,
            "world_position": d.world_position,
            "confidence": d.confidence,
        }
        for d in existing_defects_result.scalars().all()
    ]

    # Step 5: Map each detection
    from app.services.auto_mapper import DetectionInput, batch_map_detections

    all_detections: list[DetectionInput] = []
    for fd in frame_detections:
        for det in fd.detections:
            bbox = det.bbox_pixels if hasattr(det, "bbox_pixels") else det.bbox
            # Compute pixel centroid
            cx = bbox.get("x", 0) + bbox.get("w", 0) / 2.0
            cy = bbox.get("y", 0) + bbox.get("h", 0) / 2.0

            # If bbox is normalised, convert to pixel coords
            if camera.image_width and camera.image_height:
                if cx <= 1.0 and cy <= 1.0:
                    cx *= camera.image_width
                    cy *= camera.image_height

            all_detections.append(DetectionInput(
                defect_class=det.defect_class,
                confidence=det.confidence,
                severity=det.severity,
                severity_score=det.severity_score,
                pixel_x=cx,
                pixel_y=cy,
                bbox=det.bbox if hasattr(det, "bbox") else bbox,
                camera_id=str(camera.id),
                source_image_url=f"camera://{camera.name}",
            ))

    # Run batch mapping in executor (CPU-bound raycasting)
    def _map():
        return batch_map_detections(
            detections=all_detections,
            intrinsics=intrinsics,
            rotation_matrix=R,
            camera_position=cam_pos,
            candidate_meshes=candidate_meshes,
            existing_defects=existing_defects,
        )

    mapping_results = await loop.run_in_executor(None, _map) if all_detections else []

    # Step 6: Save results to DB
    result_items: list[MappingResultItem] = []
    mapped_count = 0
    dedup_count = 0
    unmapped_count = 0

    for mr in mapping_results:
        if mr.mapped_element_guid:
            if mr.was_deduplicated and mr.existing_defect_id:
                # Update existing defect
                try:
                    existing = await db.execute(
                        select(Defect).where(Defect.id == uuid.UUID(mr.existing_defect_id))
                    )
                    defect = existing.scalar_one_or_none()
                    if defect:
                        if mr.detection.confidence > defect.confidence:
                            defect.confidence = mr.detection.confidence
                            defect.severity_score = mr.detection.severity_score
                        defect.updated_at = datetime.now(timezone.utc)
                    dedup_count += 1
                except Exception as e:
                    logger.warning("Failed to update existing defect: %s", e)
            else:
                # Create new defect with mapping
                try:
                    defect = Defect(
                        project_id=camera.project_id,
                        defect_class=DefectClass(mr.detection.defect_class),
                        severity=SeverityLevel(mr.detection.severity),
                        severity_score=mr.detection.severity_score,
                        confidence=mr.detection.confidence,
                        bbox=mr.detection.bbox,
                        source_image_url=mr.detection.source_image_url,
                        status=DefectStatus.DETECTED,
                        created_by_id=user.id,
                        bim_element_guid=mr.mapped_element_guid,
                        world_position=(
                            {"x": mr.hit_position[0], "y": mr.hit_position[1], "z": mr.hit_position[2]}
                            if mr.hit_position else None
                        ),
                        notes=f"Auto-mapped from camera '{camera.name}' via PnP calibration",
                    )
                    db.add(defect)
                    mapped_count += 1
                except Exception as e:
                    logger.warning("Failed to save mapped defect: %s", e)

            result_items.append(MappingResultItem(
                defect_class=mr.detection.defect_class,
                confidence=round(mr.detection.confidence, 4),
                severity=mr.detection.severity,
                mapped_element_guid=mr.mapped_element_guid,
                hit_position=(
                    {"x": mr.hit_position[0], "y": mr.hit_position[1], "z": mr.hit_position[2]}
                    if mr.hit_position else None
                ),
                hit_distance_m=round(mr.hit_distance_m, 3) if mr.hit_distance_m else None,
                was_deduplicated=mr.was_deduplicated,
                defect_id=mr.existing_defect_id,
            ))
        else:
            unmapped_count += 1
            result_items.append(MappingResultItem(
                defect_class=mr.detection.defect_class,
                confidence=round(mr.detection.confidence, 4),
                severity=mr.detection.severity,
            ))

    # Update camera stats
    camera.last_detection_at = datetime.now(timezone.utc)
    camera.total_defects_found = (camera.total_defects_found or 0) + mapped_count

    await db.commit()

    return AutoMappingResult(
        camera_id=str(camera.id),
        camera_name=camera.name,
        frames_analyzed=len(frame_detections),
        total_detections=len(all_detections),
        mapped_count=mapped_count,
        deduplicated_count=dedup_count,
        unmapped_count=unmapped_count,
        results=result_items,
        status="completed",
    )
