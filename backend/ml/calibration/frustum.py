"""View-frustum computation and candidate-set building.

After a camera is calibrated (pose R, t known) and its field of view is
specified, this module computes which BIM elements fall inside the camera's
view frustum.  Only those elements become candidates for raycasting — this
is both a correctness measure (rules out geometrically impossible matches)
and a performance measure (far fewer elements to test per detection).

The frustum is a truncated pyramid defined by:
  - Near and far clipping planes
  - Four side planes derived from the camera's FOV and aspect ratio
  - The camera's position and orientation
"""

from __future__ import annotations

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)


def compute_frustum_planes(
    camera_position: np.ndarray,
    rotation_matrix: np.ndarray,
    fov_horizontal_deg: float,
    aspect_ratio: float = 16.0 / 9.0,
    near: float = 0.1,
    far: float = 50.0,
) -> list[tuple[np.ndarray, float]]:
    """Compute the 6 frustum planes in world space.

    Each plane is represented as (normal, d) where normal · point + d >= 0
    for points inside the frustum.

    Args:
        camera_position: (3,) camera position in world coords.
        rotation_matrix: 3×3 rotation matrix (world-to-camera).
        fov_horizontal_deg: Horizontal field of view in degrees.
        aspect_ratio: Image width / height.
        near: Near clipping distance (metres).
        far: Far clipping distance (metres).

    Returns:
        List of 6 (normal, d) tuples for [near, far, left, right, top, bottom].
    """
    # Camera axes in world space
    # R maps world → camera, so R^T maps camera → world
    R_inv = rotation_matrix.T
    forward = R_inv @ np.array([0.0, 0.0, 1.0])   # camera looks along +Z
    right_ax = R_inv @ np.array([1.0, 0.0, 0.0])
    up = R_inv @ np.array([0.0, -1.0, 0.0])  # -Y in camera = up in world

    forward = forward / np.linalg.norm(forward)
    right_ax = right_ax / np.linalg.norm(right_ax)
    up = up / np.linalg.norm(up)

    # Half angles
    h_fov = math.radians(fov_horizontal_deg / 2.0)
    v_fov = math.atan(math.tan(h_fov) / aspect_ratio)

    planes = []

    # Near plane: normal = forward, passes through camera_pos + near * forward
    near_center = camera_position + near * forward
    planes.append((forward.copy(), -np.dot(forward, near_center)))

    # Far plane: normal = -forward, passes through camera_pos + far * forward
    far_center = camera_position + far * forward
    planes.append((-forward.copy(), np.dot(forward, far_center)))

    # Left plane
    left_normal = np.cos(h_fov) * right_ax + np.sin(h_fov) * forward
    left_normal = left_normal / np.linalg.norm(left_normal)
    planes.append((left_normal, -np.dot(left_normal, camera_position)))

    # Right plane
    right_normal = -np.cos(h_fov) * right_ax + np.sin(h_fov) * forward
    right_normal = right_normal / np.linalg.norm(right_normal)
    planes.append((right_normal, -np.dot(right_normal, camera_position)))

    # Top plane
    top_normal = -np.cos(v_fov) * up + np.sin(v_fov) * forward
    top_normal = top_normal / np.linalg.norm(top_normal)
    planes.append((top_normal, -np.dot(top_normal, camera_position)))

    # Bottom plane
    bottom_normal = np.cos(v_fov) * up + np.sin(v_fov) * forward
    bottom_normal = bottom_normal / np.linalg.norm(bottom_normal)
    planes.append((bottom_normal, -np.dot(bottom_normal, camera_position)))

    return planes


def is_bbox_in_frustum(
    bbox_min: np.ndarray,
    bbox_max: np.ndarray,
    planes: list[tuple[np.ndarray, float]],
) -> bool:
    """Test if an axis-aligned bounding box is (partially) inside a frustum.

    Uses the "positive vertex" test: for each frustum plane, find the
    corner of the AABB most in the direction of the plane normal.  If
    that corner is on the negative side, the entire box is outside.
    """
    for normal, d in planes:
        # Positive vertex: the AABB corner furthest in the normal direction
        p = np.array([
            bbox_max[0] if normal[0] >= 0 else bbox_min[0],
            bbox_max[1] if normal[1] >= 0 else bbox_min[1],
            bbox_max[2] if normal[2] >= 0 else bbox_min[2],
        ])
        if np.dot(normal, p) + d < 0:
            return False
    return True


def compute_candidate_set(
    camera_position: np.ndarray,
    rotation_matrix: np.ndarray,
    fov_horizontal_deg: float,
    element_meshes: dict[str, tuple[np.ndarray, np.ndarray]],
    aspect_ratio: float = 16.0 / 9.0,
    near: float = 0.1,
    far: float = 50.0,
) -> list[str]:
    """Determine which BIM elements are inside a camera's view frustum.

    This is computed once after calibration and stored on the camera record.
    Raycasting at detection time is restricted to this set.

    Args:
        camera_position: (3,) camera world position.
        rotation_matrix: 3×3 rotation matrix (world-to-camera).
        fov_horizontal_deg: Horizontal FOV in degrees.
        element_meshes: Dict mapping GUID → (vertices, faces).
        aspect_ratio: Image aspect ratio (width / height).
        near: Near clip distance.
        far: Far clip distance.

    Returns:
        List of GUIDs for elements (partially) inside the frustum.
    """
    planes = compute_frustum_planes(
        camera_position, rotation_matrix, fov_horizontal_deg,
        aspect_ratio, near, far,
    )

    candidates: list[str] = []

    for guid, (vertices, _faces) in element_meshes.items():
        if len(vertices) == 0:
            continue

        # Compute AABB
        bbox_min = vertices.min(axis=0)
        bbox_max = vertices.max(axis=0)

        if is_bbox_in_frustum(bbox_min, bbox_max, planes):
            candidates.append(guid)

    logger.info(
        "Candidate set: %d / %d elements inside frustum (FOV=%.0f°, far=%.0fm)",
        len(candidates), len(element_meshes), fov_horizontal_deg, far,
    )
    return candidates
