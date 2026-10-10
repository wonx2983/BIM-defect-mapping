"""Automated defect-to-BIM mapping service.

This is the core of Phase 2: given a detection (class, confidence, camera_id,
pixel_location), it automatically determines which BIM element the defect
belongs to and records it, with de-duplication.

Pipeline per detection:
  1. Look up the camera's calibrated pose and intrinsics.
  2. Convert the defect's pixel centroid to a 3D ray.
  3. Raycast against the camera's candidate BIM elements.
  4. Nearest hit → the element GUID.
  5. De-duplicate: same GUID + same class + nearby 3D position → update existing.
  6. Save or update the defect record.

Multi-camera conflict resolution:
  When two cameras report a detection on the same element with the same class,
  the higher-confidence detection wins.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ml.calibration.pose_solver import CameraIntrinsics
from ml.calibration.raycaster import RayHit, pixel_to_ray

logger = logging.getLogger(__name__)

# De-duplication tolerance: two detections on the same element, same class,
# within this 3D distance (metres) are considered the same real-world defect.
DEDUP_DISTANCE_TOLERANCE_M = 0.5


@dataclass
class DetectionInput:
    """A single defect detection from the upstream YOLO pipeline."""

    defect_class: str
    confidence: float
    severity: str
    severity_score: float
    pixel_x: float  # bbox centroid x
    pixel_y: float  # bbox centroid y
    bbox: dict  # {x, y, w, h} normalised
    camera_id: str  # UUID string
    timestamp_ms: int = 0
    source_image_url: str = ""


@dataclass
class MappingResult:
    """Result of mapping a single detection."""

    detection: DetectionInput
    mapped_element_guid: str | None = None
    hit_position: tuple[float, float, float] | None = None
    hit_distance_m: float | None = None
    was_deduplicated: bool = False
    existing_defect_id: str | None = None
    error: str | None = None


def map_detection_to_element(
    detection: DetectionInput,
    intrinsics: CameraIntrinsics,
    rotation_matrix: np.ndarray,
    camera_position: np.ndarray,
    candidate_meshes: dict[str, tuple[np.ndarray, np.ndarray]],
    max_distance: float = 50.0,
) -> MappingResult:
    """Map a single detection to a BIM element via raycasting.

    Args:
        detection: The upstream detection record.
        intrinsics: Camera intrinsic parameters.
        rotation_matrix: 3×3 rotation matrix from calibration.
        camera_position: Camera world position from calibration.
        candidate_meshes: Dict of GUID → (vertices, faces) for candidate elements.
        max_distance: Maximum ray distance (metres).

    Returns:
        ``MappingResult`` with the mapped element GUID or an error.
    """
    # Step 1: Convert pixel to ray
    ray = pixel_to_ray(
        u=detection.pixel_x,
        v=detection.pixel_y,
        fx=intrinsics.fx,
        fy=intrinsics.fy,
        cx=intrinsics.cx,
        cy=intrinsics.cy,
        rotation_matrix=rotation_matrix,
        camera_position=camera_position,
    )

    # Step 2: Try trimesh-accelerated raycasting first, fall back to pure numpy
    hit: RayHit | None = None

    try:
        import trimesh
        # Convert raw vertex/face arrays to trimesh objects for acceleration
        trimesh_meshes = {}
        for guid, (verts, faces) in candidate_meshes.items():
            try:
                tm = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
                trimesh_meshes[guid] = tm
            except Exception:
                continue

        if trimesh_meshes:
            from ml.calibration.raycaster import raycast_against_trimeshes
            hit = raycast_against_trimeshes(ray, trimesh_meshes, max_distance)
    except ImportError:
        pass

    # Fallback: pure numpy Möller–Trumbore
    if hit is None and candidate_meshes:
        from ml.calibration.raycaster import raycast_against_meshes
        hit = raycast_against_meshes(ray, candidate_meshes, max_distance)

    if hit is None:
        return MappingResult(
            detection=detection,
            error="Ray did not intersect any candidate BIM element",
        )

    return MappingResult(
        detection=detection,
        mapped_element_guid=hit.element_guid,
        hit_position=(
            float(hit.hit_point[0]),
            float(hit.hit_point[1]),
            float(hit.hit_point[2]),
        ),
        hit_distance_m=hit.distance,
    )


def deduplicate_detection(
    result: MappingResult,
    existing_defects: list[dict],
    tolerance_m: float = DEDUP_DISTANCE_TOLERANCE_M,
) -> MappingResult:
    """Check if this detection matches an existing defect record.

    A match is defined as: same element GUID + same defect class +
    3D position within ``tolerance_m`` metres.

    If matched, the result is marked as de-duplicated and the existing
    defect ID is set (so the caller can update rather than create).

    Args:
        result: The mapping result from ``map_detection_to_element``.
        existing_defects: List of dicts with at least:
            - ``id``: defect UUID string
            - ``bim_element_guid``: str or None
            - ``defect_class``: str
            - ``world_position``: dict {x, y, z} or None
            - ``confidence``: float
        tolerance_m: 3D distance threshold for considering two positions
                     as the same real-world defect.

    Returns:
        The same ``MappingResult``, potentially with ``was_deduplicated=True``
        and ``existing_defect_id`` set.
    """
    if not result.mapped_element_guid or not result.hit_position:
        return result

    hit_pos = np.array(result.hit_position)

    for existing in existing_defects:
        # Must match on element and class
        if existing.get("bim_element_guid") != result.mapped_element_guid:
            continue
        if existing.get("defect_class") != result.detection.defect_class:
            continue

        # Check 3D distance
        existing_pos = existing.get("world_position")
        if existing_pos and isinstance(existing_pos, dict):
            ex_pos = np.array([
                existing_pos.get("x", 0),
                existing_pos.get("y", 0),
                existing_pos.get("z", 0),
            ])
            distance = float(np.linalg.norm(hit_pos - ex_pos))
            if distance <= tolerance_m:
                # Multi-camera conflict: prefer higher confidence
                if result.detection.confidence > existing.get("confidence", 0):
                    result.was_deduplicated = True
                    result.existing_defect_id = existing["id"]
                    logger.info(
                        "De-dup: updating defect %s (higher confidence %.3f > %.3f)",
                        existing["id"], result.detection.confidence,
                        existing.get("confidence", 0),
                    )
                else:
                    result.was_deduplicated = True
                    result.existing_defect_id = existing["id"]
                    logger.info(
                        "De-dup: existing defect %s has equal/higher confidence, "
                        "will update last_seen only",
                        existing["id"],
                    )
                return result

    return result


def batch_map_detections(
    detections: list[DetectionInput],
    intrinsics: CameraIntrinsics,
    rotation_matrix: np.ndarray,
    camera_position: np.ndarray,
    candidate_meshes: dict[str, tuple[np.ndarray, np.ndarray]],
    existing_defects: list[dict],
    max_distance: float = 50.0,
) -> list[MappingResult]:
    """Map and de-duplicate a batch of detections from a single camera.

    This is the main entry point for the auto-mapping pipeline.

    Args:
        detections: List of upstream detections.
        intrinsics: Camera intrinsics.
        rotation_matrix: 3×3 rotation matrix.
        camera_position: Camera world position.
        candidate_meshes: GUID → (vertices, faces) for this camera's candidates.
        existing_defects: Current defect records for de-duplication.
        max_distance: Maximum raycasting distance.

    Returns:
        List of ``MappingResult`` with mapping and dedup results.
    """
    results: list[MappingResult] = []

    for det in detections:
        result = map_detection_to_element(
            detection=det,
            intrinsics=intrinsics,
            rotation_matrix=rotation_matrix,
            camera_position=camera_position,
            candidate_meshes=candidate_meshes,
            max_distance=max_distance,
        )

        if result.mapped_element_guid:
            # De-duplicate against existing + already-mapped in this batch
            all_existing = existing_defects + [
                {
                    "id": str(uuid.uuid4()),  # placeholder
                    "bim_element_guid": r.mapped_element_guid,
                    "defect_class": r.detection.defect_class,
                    "world_position": (
                        {"x": r.hit_position[0], "y": r.hit_position[1], "z": r.hit_position[2]}
                        if r.hit_position else None
                    ),
                    "confidence": r.detection.confidence,
                }
                for r in results
                if r.mapped_element_guid and not r.was_deduplicated
            ]
            result = deduplicate_detection(result, all_existing)

        results.append(result)

    mapped = sum(1 for r in results if r.mapped_element_guid)
    deduped = sum(1 for r in results if r.was_deduplicated)
    unmapped = sum(1 for r in results if r.error)

    logger.info(
        "Batch mapping: %d detections → %d mapped, %d de-duplicated, %d unmapped",
        len(detections), mapped, deduped, unmapped,
    )

    return results
