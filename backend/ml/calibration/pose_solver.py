"""PnP pose solver — recovers a camera's 3D pose from known 2D–3D correspondences.

Given a fiducial marker whose 3D position is known from the BIM model and
whose 2D corners are detected in a camera frame, this module solves the
Perspective-n-Point (PnP) problem to determine the camera's rotation ``R``
and translation ``t`` in the BIM's world coordinate system.

The math:
    s * [u, v, 1]^T = K * (R * P + t)

Where K is the camera intrinsic matrix, R is rotation, t is translation,
P is a 3D world point, and (u, v) is the observed pixel.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CameraIntrinsics:
    """Camera intrinsic parameters.

    Attributes:
        fx: Focal length in pixels (horizontal).
        fy: Focal length in pixels (vertical).
        cx: Principal point x (pixels), typically image_width / 2.
        cy: Principal point y (pixels), typically image_height / 2.
        dist_coeffs: Lens distortion coefficients [k1, k2, p1, p2, k3].
                     Default zeros (no distortion).
    """

    fx: float
    fy: float
    cx: float
    cy: float
    dist_coeffs: np.ndarray | None = None

    @property
    def matrix(self) -> np.ndarray:
        """Return the 3×3 camera intrinsic matrix K."""
        return np.array([
            [self.fx, 0.0, self.cx],
            [0.0, self.fy, self.cy],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)

    @property
    def dist(self) -> np.ndarray:
        """Return distortion coefficients (5,) array."""
        if self.dist_coeffs is not None:
            return np.asarray(self.dist_coeffs, dtype=np.float64).ravel()
        return np.zeros(5, dtype=np.float64)

    def to_dict(self) -> dict:
        """Serialise to JSON-safe dict for database storage."""
        d: dict = {"fx": self.fx, "fy": self.fy, "cx": self.cx, "cy": self.cy}
        if self.dist_coeffs is not None:
            d["dist_coeffs"] = self.dist_coeffs.tolist() if isinstance(
                self.dist_coeffs, np.ndarray,
            ) else list(self.dist_coeffs)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> CameraIntrinsics:
        """Reconstruct from a dict (e.g. loaded from the database)."""
        dc = data.get("dist_coeffs")
        return cls(
            fx=float(data["fx"]),
            fy=float(data["fy"]),
            cx=float(data["cx"]),
            cy=float(data["cy"]),
            dist_coeffs=np.array(dc, dtype=np.float64) if dc else None,
        )

    @classmethod
    def from_fov(
        cls,
        fov_horizontal_deg: float,
        image_width: int,
        image_height: int,
    ) -> CameraIntrinsics:
        """Compute intrinsics from horizontal field of view and image dimensions.

        fx = (image_width / 2) / tan(fov_horizontal / 2)
        """
        fov_rad = math.radians(fov_horizontal_deg)
        fx = (image_width / 2.0) / math.tan(fov_rad / 2.0)
        fy = fx  # square pixels assumed
        cx = image_width / 2.0
        cy = image_height / 2.0
        return cls(fx=fx, fy=fy, cx=cx, cy=cy)


@dataclass(frozen=True)
class PnPResult:
    """Result of a PnP solve.

    Attributes:
        success: Whether the solve converged.
        rvec: Rodrigues rotation vector (3,).
        tvec: Translation vector (3,).
        rotation_matrix: 3×3 rotation matrix.
        reprojection_error: Mean reprojection error in pixels.
        camera_position_world: Camera position in world coordinates.
    """

    success: bool
    rvec: np.ndarray | None = None
    tvec: np.ndarray | None = None
    rotation_matrix: np.ndarray | None = None
    reprojection_error: float = float("inf")
    camera_position_world: np.ndarray | None = None


def marker_object_points(physical_size_m: float) -> np.ndarray:
    """Return the 4 corner 3D coordinates of a flat square marker.

    Corners are relative to the marker's centre, in the marker's local
    coordinate system (Z = 0 plane):
        [(-s/2, +s/2, 0), (+s/2, +s/2, 0), (+s/2, -s/2, 0), (-s/2, -s/2, 0)]

    This matches OpenCV's ArUco corner ordering:
        top-left, top-right, bottom-right, bottom-left.
    """
    half = physical_size_m / 2.0
    return np.array([
        [-half, +half, 0.0],
        [+half, +half, 0.0],
        [+half, -half, 0.0],
        [-half, -half, 0.0],
    ], dtype=np.float64)


def transform_object_points_to_world(
    object_points: np.ndarray,
    world_position: tuple[float, float, float],
    surface_normal: tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> np.ndarray:
    """Transform marker-local object points into BIM world coordinates.

    The marker is placed at ``world_position`` on a surface with the given
    normal.  We compute a rotation that maps the marker's local Z axis to
    the surface normal, then translate to the world position.
    """
    pos = np.array(world_position, dtype=np.float64)
    normal = np.array(surface_normal, dtype=np.float64)
    normal = normal / (np.linalg.norm(normal) + 1e-12)

    # Build rotation from marker-local frame (Z-up) to world frame
    z_axis = normal
    # Choose an arbitrary perpendicular axis for X
    up = np.array([0.0, 1.0, 0.0])
    if abs(np.dot(z_axis, up)) > 0.9:
        up = np.array([1.0, 0.0, 0.0])
    x_axis = np.cross(up, z_axis)
    x_axis = x_axis / (np.linalg.norm(x_axis) + 1e-12)
    y_axis = np.cross(z_axis, x_axis)

    rotation = np.column_stack([x_axis, y_axis, z_axis])  # 3×3

    # Transform each point: world = R * local + pos
    world_points = (rotation @ object_points.T).T + pos
    return world_points.astype(np.float64)


def solve_pnp(
    image_points: np.ndarray,
    object_points_world: np.ndarray,
    intrinsics: CameraIntrinsics,
    use_ransac: bool = True,
) -> PnPResult:
    """Solve PnP to recover camera pose from 2D–3D correspondences.

    Args:
        image_points: (N, 2) array of pixel coordinates.
        object_points_world: (N, 3) array of corresponding 3D world coordinates.
        intrinsics: Camera intrinsic parameters.
        use_ransac: Whether to use RANSAC for outlier rejection.

    Returns:
        ``PnPResult`` with the camera's rotation, translation, and error.
    """
    assert image_points.shape[0] >= 4, "PnP requires at least 4 point correspondences"
    assert image_points.shape[0] == object_points_world.shape[0]

    obj_pts = object_points_world.astype(np.float64)
    img_pts = image_points.astype(np.float64)
    K = intrinsics.matrix
    dist = intrinsics.dist

    if use_ransac and image_points.shape[0] >= 4:
        success, rvec, tvec, inliers = cv2.solvePnPRansac(
            obj_pts, img_pts, K, dist,
            iterationsCount=200,
            reprojectionError=5.0,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if success and inliers is not None:
            logger.info("PnP RANSAC: %d/%d inliers", len(inliers), len(img_pts))
    else:
        success, rvec, tvec = cv2.solvePnP(
            obj_pts, img_pts, K, dist,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )

    if not success:
        logger.warning("PnP solve failed — no valid pose found")
        return PnPResult(success=False)

    # Refine with Levenberg-Marquardt
    rvec, tvec = cv2.solvePnPRefineLM(obj_pts, img_pts, K, dist, rvec, tvec)

    # Compute rotation matrix
    R, _ = cv2.Rodrigues(rvec)

    # Compute reprojection error
    projected, _ = cv2.projectPoints(obj_pts, rvec, tvec, K, dist)
    projected = projected.reshape(-1, 2)
    errors = np.linalg.norm(projected - img_pts, axis=1)
    mean_error = float(errors.mean())

    # Camera position in world coordinates: C = -R^T * t
    camera_pos_world = -R.T @ tvec.ravel()

    logger.info(
        "PnP solved: reprojection error = %.2f px, camera at (%.2f, %.2f, %.2f)",
        mean_error, *camera_pos_world,
    )

    return PnPResult(
        success=True,
        rvec=rvec.ravel(),
        tvec=tvec.ravel(),
        rotation_matrix=R,
        reprojection_error=mean_error,
        camera_position_world=camera_pos_world,
    )


def compute_reprojection_error(
    image_points: np.ndarray,
    object_points_world: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
    intrinsics: CameraIntrinsics,
) -> float:
    """Compute mean reprojection error for a given pose.

    Useful for validating a stored calibration: re-detect the marker,
    re-project the known 3D points through the stored pose, and confirm
    the error is still small.
    """
    K = intrinsics.matrix
    dist = intrinsics.dist
    projected, _ = cv2.projectPoints(
        object_points_world.astype(np.float64),
        rvec.astype(np.float64),
        tvec.astype(np.float64),
        K, dist,
    )
    projected = projected.reshape(-1, 2)
    errors = np.linalg.norm(projected - image_points.astype(np.float64), axis=1)
    return float(errors.mean())
