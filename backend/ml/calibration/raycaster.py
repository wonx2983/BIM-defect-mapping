"""Pixel-to-ray conversion and ray-mesh intersection for BIM element mapping.

This module implements the core geometric operations of the automated
defect-to-BIM mapping pipeline:

1. **Pixel → 3D ray**: Given a pixel coordinate and a calibrated camera
   pose, compute the corresponding 3D ray direction in world space.

2. **Ray → BIM element**: Intersect the ray against candidate BIM element
   meshes (triangulated surfaces) and return the nearest hit.

The raycasting is intentionally restricted to a candidate set of elements
(those inside the camera's view frustum) for both correctness and
performance — see ``frustum.py`` for how the candidate set is computed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Ray:
    """A 3D ray with an origin and direction.

    Attributes:
        origin: (3,) array — starting point (camera position in world coords).
        direction: (3,) array — normalised direction vector.
    """

    origin: np.ndarray
    direction: np.ndarray


@dataclass(frozen=True)
class RayHit:
    """Result of a ray-mesh intersection.

    Attributes:
        element_guid: GUID of the BIM element that was hit.
        hit_point: (3,) array — world-space intersection point.
        distance: Distance from ray origin to hit point (metres).
        face_index: Triangle index within the element's mesh.
    """

    element_guid: str
    hit_point: np.ndarray
    distance: float
    face_index: int = -1


def pixel_to_ray(
    u: float,
    v: float,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    rotation_matrix: np.ndarray,
    camera_position: np.ndarray,
) -> Ray:
    """Convert a pixel coordinate into a 3D ray in world space.

    Uses the inverse of the pinhole camera model:
        direction_camera = normalise([(u - cx) / fx, (v - cy) / fy, 1])
        direction_world  = R^T * direction_camera

    Args:
        u, v: Pixel coordinates (can be sub-pixel floats).
        fx, fy, cx, cy: Camera intrinsic parameters.
        rotation_matrix: 3×3 rotation matrix (camera → world).
        camera_position: Camera position in world coordinates (3,).

    Returns:
        A ``Ray`` originating at the camera position.
    """
    # Direction in camera-local space
    dir_cam = np.array([
        (u - cx) / fx,
        (v - cy) / fy,
        1.0,
    ], dtype=np.float64)

    # Normalise
    dir_cam = dir_cam / np.linalg.norm(dir_cam)

    # Transform to world space: R^T maps camera frame → world frame
    dir_world = rotation_matrix.T @ dir_cam
    dir_world = dir_world / np.linalg.norm(dir_world)

    return Ray(
        origin=np.asarray(camera_position, dtype=np.float64),
        direction=dir_world,
    )


def _ray_triangle_intersection(
    ray_origin: np.ndarray,
    ray_dir: np.ndarray,
    v0: np.ndarray,
    v1: np.ndarray,
    v2: np.ndarray,
    epsilon: float = 1e-8,
) -> float | None:
    """Möller–Trumbore ray-triangle intersection.

    Returns the distance ``t`` along the ray if the ray intersects the
    triangle, or ``None`` if there is no intersection.
    """
    edge1 = v1 - v0
    edge2 = v2 - v0
    h = np.cross(ray_dir, edge2)
    a = np.dot(edge1, h)

    if -epsilon < a < epsilon:
        return None  # Ray is parallel to triangle

    f = 1.0 / a
    s = ray_origin - v0
    u = f * np.dot(s, h)
    if u < 0.0 or u > 1.0:
        return None

    q = np.cross(s, edge1)
    v = f * np.dot(ray_dir, q)
    if v < 0.0 or u + v > 1.0:
        return None

    t = f * np.dot(edge2, q)
    if t > epsilon:
        return float(t)

    return None


def raycast_against_meshes(
    ray: Ray,
    candidate_meshes: dict[str, tuple[np.ndarray, np.ndarray]],
    max_distance: float = 100.0,
) -> RayHit | None:
    """Cast a ray against a set of candidate BIM element meshes.

    Finds the **nearest** intersection across all candidate elements,
    implementing the "nearest hit = element" rule from the plan (§4.2 Step 4).

    Args:
        ray: The 3D ray to cast.
        candidate_meshes: Dict mapping element GUID → (vertices, faces).
            - vertices: (N, 3) float array of vertex positions.
            - faces: (M, 3) int array of triangle vertex indices.
        max_distance: Ignore hits beyond this distance (metres).

    Returns:
        ``RayHit`` for the nearest intersected element, or ``None`` if
        the ray misses all candidates.
    """
    best_hit: RayHit | None = None
    best_dist = max_distance

    for guid, (vertices, faces) in candidate_meshes.items():
        for face_idx, face in enumerate(faces):
            v0, v1, v2 = vertices[face[0]], vertices[face[1]], vertices[face[2]]
            t = _ray_triangle_intersection(ray.origin, ray.direction, v0, v1, v2)
            if t is not None and 0 < t < best_dist:
                hit_point = ray.origin + t * ray.direction
                best_dist = t
                best_hit = RayHit(
                    element_guid=guid,
                    hit_point=hit_point,
                    distance=t,
                    face_index=face_idx,
                )

    if best_hit:
        logger.debug(
            "Ray hit element %s at distance %.2f m",
            best_hit.element_guid, best_hit.distance,
        )
    else:
        logger.debug("Ray missed all %d candidate elements", len(candidate_meshes))

    return best_hit


def raycast_against_trimeshes(
    ray: Ray,
    candidate_meshes: dict,
    max_distance: float = 100.0,
) -> RayHit | None:
    """Cast a ray against trimesh.Trimesh objects (accelerated with embree if available).

    This is the preferred path when ``trimesh`` is installed, as it uses
    spatial acceleration structures (BVH / embree) for much faster
    intersection than the naive triangle-by-triangle approach.

    Args:
        ray: The 3D ray to cast.
        candidate_meshes: Dict mapping element GUID → trimesh.Trimesh.
        max_distance: Ignore hits beyond this distance.

    Returns:
        ``RayHit`` for the nearest element, or ``None``.
    """
    best_hit: RayHit | None = None
    best_dist = max_distance

    origins = ray.origin.reshape(1, 3)
    directions = ray.direction.reshape(1, 3)

    for guid, mesh in candidate_meshes.items():
        try:
            locations, index_ray, index_tri = mesh.ray.intersects_location(
                ray_origins=origins,
                ray_directions=directions,
            )

            if len(locations) == 0:
                continue

            # Find the nearest hit for this element
            distances = np.linalg.norm(locations - ray.origin, axis=1)
            nearest_idx = int(np.argmin(distances))
            dist = float(distances[nearest_idx])

            if 0 < dist < best_dist:
                best_dist = dist
                best_hit = RayHit(
                    element_guid=guid,
                    hit_point=locations[nearest_idx],
                    distance=dist,
                    face_index=int(index_tri[nearest_idx]),
                )
        except Exception as e:
            logger.warning("Ray-mesh intersection failed for element %s: %s", guid, e)
            continue

    return best_hit
