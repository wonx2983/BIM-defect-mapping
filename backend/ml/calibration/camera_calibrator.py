"""Camera calibrator — orchestrates the full calibration pipeline.

Flow:
  1. Grab a frame from the camera's RTSP stream.
  2. Detect ArUco markers in the frame.
  3. Match detected marker IDs against the marker registry.
  4. Build 2D–3D correspondences (pixel corners ↔ world coordinates).
  5. Solve PnP to recover the camera's pose (R, t).
  6. Validate via reprojection error.
  7. Compute the candidate element set (frustum test against BIM).
  8. Store everything on the camera record.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ml.calibration.marker_detector import detect_markers, grab_frame_from_rtsp
from ml.calibration.pose_solver import (
    CameraIntrinsics,
    PnPResult,
    marker_object_points,
    solve_pnp,
    transform_object_points_to_world,
)

logger = logging.getLogger(__name__)


@dataclass
class CalibrationResult:
    """Result of the full calibration pipeline."""

    success: bool
    detected_marker_id: int | None = None
    registry_marker_id: str | None = None  # UUID str from the DB
    intrinsics: CameraIntrinsics | None = None
    pnp_result: PnPResult | None = None
    candidate_guids: list[str] | None = None
    image_width: int | None = None
    image_height: int | None = None
    error_message: str = ""


def calibrate_camera_from_frame(
    frame: np.ndarray,
    marker_registry: list[dict],
    intrinsics: CameraIntrinsics | None = None,
    fov_horizontal_deg: float | None = None,
    aruco_dict_type: str = "DICT_4X4_50",
    ifc_path: str | Path | None = None,
) -> CalibrationResult:
    """Run the full calibration pipeline on a single frame.

    Args:
        frame: BGR image from the camera.
        marker_registry: List of dicts from the DB, each with:
            - ``id``: UUID string
            - ``marker_dict_id``: int (ArUco ID)
            - ``aruco_dict_type``: str
            - ``world_x``, ``world_y``, ``world_z``: float
            - ``normal_x``, ``normal_y``, ``normal_z``: float
            - ``physical_size_m``: float
        intrinsics: Pre-computed intrinsics, or ``None`` to derive from FOV.
        fov_horizontal_deg: Used if ``intrinsics`` is None.
        aruco_dict_type: ArUco dictionary to use for detection.
        ifc_path: Optional IFC file path for candidate-set computation.

    Returns:
        ``CalibrationResult`` with the camera's pose or an error message.
    """
    h, w = frame.shape[:2]

    # Step 1: Determine intrinsics
    if intrinsics is None:
        if fov_horizontal_deg is None:
            return CalibrationResult(
                success=False,
                error_message="Either intrinsics or fov_horizontal_deg must be provided",
                image_width=w,
                image_height=h,
            )
        intrinsics = CameraIntrinsics.from_fov(fov_horizontal_deg, w, h)
        logger.info(
            "Computed intrinsics from FOV=%.1f°: fx=%.1f, fy=%.1f, cx=%.1f, cy=%.1f",
            fov_horizontal_deg, intrinsics.fx, intrinsics.fy, intrinsics.cx, intrinsics.cy,
        )

    # Step 2: Detect ArUco markers
    matches = []
    detected = []
    dictionaries = {entry.get("aruco_dict_type", aruco_dict_type) for entry in marker_registry}
    for dictionary in sorted(dictionaries):
        registry = {entry["marker_dict_id"]: entry for entry in marker_registry
                    if entry.get("aruco_dict_type", aruco_dict_type) == dictionary}
        found = detect_markers(frame, dict_type=dictionary)
        detected.extend(found)
        matches.extend((marker, registry[marker.marker_id]) for marker in found
                       if marker.marker_id in registry)
    if not detected:
        return CalibrationResult(
            success=False,
            intrinsics=intrinsics,
            error_message="No ArUco markers detected in the frame. "
                          "Ensure the marker is clearly visible, well-lit, "
                          "and matches the selected dictionary type.",
            image_width=w,
            image_height=h,
        )

    # Step 3: Match against registry
    if not matches:
        return CalibrationResult(success=False, intrinsics=intrinsics,
            image_width=w, image_height=h,
            error_message="At least one registered marker must be visible for calibration.")
    matched_marker, matched_registry = matches[0]
    image_points, world_points = [], []
    for marker, entry in matches:
        image_points.append(marker.corners)
        world_points.append(transform_object_points_to_world(
            marker_object_points(entry["physical_size_m"]),
            (entry["world_x"], entry["world_y"], entry["world_z"]),
            (entry.get("normal_x", 0), entry.get("normal_y", 0), entry.get("normal_z", 1)),
            entry.get("rotation_deg", 0),
        ))
    pnp_result = solve_pnp(np.vstack(image_points), np.vstack(world_points),
                           intrinsics, use_ransac=len(matches) > 1)

    if not pnp_result.success:
        return CalibrationResult(
            success=False,
            detected_marker_id=matched_marker.marker_id,
            registry_marker_id=str(matched_registry["id"]),
            intrinsics=intrinsics,
            error_message="PnP solve failed — could not determine camera pose. "
                          "Try a different camera angle or marker position.",
            image_width=w,
            image_height=h,
        )

    # A converged optimizer is not necessarily a usable calibration.
    if not np.isfinite(pnp_result.reprojection_error) or pnp_result.reprojection_error > 2.0:
        return CalibrationResult(success=False, intrinsics=intrinsics,
            image_width=w, image_height=h,
            error_message="Calibration rejected: reprojection error exceeds 2 pixels.")

    # Step 7: Compute candidate set (if IFC path provided)
    candidate_guids: list[str] | None = None
    if ifc_path is not None:
        try:
            from ml.calibration.frustum import compute_candidate_set
            from ml.calibration.ifc_geometry import extract_meshes_from_ifc

            meshes = extract_meshes_from_ifc(ifc_path)
            fov = float(np.degrees(2 * np.arctan(w / (2 * intrinsics.fx))))
            aspect = w / h if h > 0 else 16.0 / 9.0

            candidate_guids = compute_candidate_set(
                camera_position=pnp_result.camera_position_world,
                rotation_matrix=pnp_result.rotation_matrix,
                fov_horizontal_deg=fov,
                element_meshes=meshes,
                aspect_ratio=aspect,
            )
            logger.info("Computed %d candidate elements", len(candidate_guids))
        except ImportError:
            logger.warning("ifcopenshell not installed — skipping candidate-set computation")
        except Exception as e:
            logger.warning("Candidate-set computation failed: %s", e)

    return CalibrationResult(
        success=True,
        detected_marker_id=matched_marker.marker_id,
        registry_marker_id=str(matched_registry["id"]),
        intrinsics=intrinsics,
        pnp_result=pnp_result,
        candidate_guids=candidate_guids,
        image_width=w,
        image_height=h,
    )


def calibrate_camera_from_rtsp(
    rtsp_url: str,
    marker_registry: list[dict],
    intrinsics: CameraIntrinsics | None = None,
    fov_horizontal_deg: float | None = None,
    aruco_dict_type: str = "DICT_4X4_50",
    ifc_path: str | Path | None = None,
) -> CalibrationResult:
    """Convenience: grab a frame from RTSP and run calibration.

    See ``calibrate_camera_from_frame`` for parameter details.
    """
    try:
        frame = grab_frame_from_rtsp(rtsp_url)
    except RuntimeError as e:
        return CalibrationResult(
            success=False,
            error_message=f"Failed to grab frame from RTSP: {e}",
        )

    return calibrate_camera_from_frame(
        frame=frame,
        marker_registry=marker_registry,
        intrinsics=intrinsics,
        fov_horizontal_deg=fov_horizontal_deg,
        aruco_dict_type=aruco_dict_type,
        ifc_path=ifc_path,
    )
