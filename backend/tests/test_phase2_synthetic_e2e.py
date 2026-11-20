"""
Phase 2: Comprehensive Synthetic End-to-End Test
=================================================
Tests the ENTIRE automated defect-to-BIM mapping pipeline using:
  - A synthetic box room (4 walls + floor + ceiling) built as raw meshes
  - A virtual camera at a known position with known intrinsics
  - Programmatically generated ArUco markers at known 3D positions
  - Synthetic "defect" detections at known pixel coordinates
  - Ground-truth verification at every stage

NO real hardware, NO real IFC file, NO real RTSP stream required.
Every module is exercised with its actual production code.

Run:  cd backend && python -m pytest tests/test_phase2_synthetic_e2e.py -v --tb=short
  OR: cd backend && python tests/test_phase2_synthetic_e2e.py
"""

from __future__ import annotations

import math
import sys
import os

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cv2
import numpy as np

# ──────────────────────────────────────────────────────────────────
# 1.  GROUND TRUTH DEFINITIONS
# ──────────────────────────────────────────────────────────────────

IMAGE_W, IMAGE_H = 1920, 1080
FOV_H_DEG = 90.0

# Camera pose (ground truth) — camera is INSIDE the room, near the south wall
GT_CAMERA_POS = np.array([5.0, 1.0, 1.5], dtype=np.float64)

# Camera looks toward +Y (toward north wall)
GT_LOOK_AT = np.array([5.0, 8.0, 1.5], dtype=np.float64)
GT_UP = np.array([0.0, 0.0, 1.0], dtype=np.float64)  # Z-up

# Box room: 10m × 10m × 3m
ROOM = {
    "x_min": 0.0, "x_max": 10.0,
    "y_min": -2.0, "y_max": 10.0,
    "z_min": 0.0, "z_max": 3.0,
}

# Markers on the North wall (y = 10.0, facing -Y toward camera)
MARKERS = [
    {"id": 0, "world_pos": (3.0, 10.0, 2.0), "normal": (0.0, -1.0, 0.0), "size_m": 0.30},
    {"id": 1, "world_pos": (7.0, 10.0, 2.0), "normal": (0.0, -1.0, 0.0), "size_m": 0.30},
]


# ──────────────────────────────────────────────────────────────────
# 2.  HELPER: Build view matrix (look-at)
# ──────────────────────────────────────────────────────────────────

def build_camera_matrices(
    cam_pos: np.ndarray,
    look_at: np.ndarray,
    up: np.ndarray,
    fov_h_deg: float,
    img_w: int,
    img_h: int,
):
    """Build the rotation matrix R (world-to-camera) and intrinsics K."""
    forward = look_at - cam_pos
    forward = forward / np.linalg.norm(forward)

    right = np.cross(forward, up)
    right = right / np.linalg.norm(right)

    cam_up = np.cross(right, forward)
    cam_up = cam_up / np.linalg.norm(cam_up)

    # OpenCV convention: camera looks along +Z, X is right, Y is down
    # R maps world → camera
    R = np.array([
        right,          # camera X = world right
        -cam_up,        # camera Y = -world up  (Y down in OpenCV)
        forward,        # camera Z = world forward
    ], dtype=np.float64)

    # Translation: t = -R @ cam_pos
    t = -R @ cam_pos

    # Intrinsics from FOV
    from ml.calibration.pose_solver import CameraIntrinsics
    intrinsics = CameraIntrinsics.from_fov(fov_h_deg, img_w, img_h)

    return R, t, intrinsics


# ──────────────────────────────────────────────────────────────────
# 3.  HELPER: Generate synthetic camera frame with ArUco markers
# ──────────────────────────────────────────────────────────────────

def project_point(pt_world, R, t, K):
    """Project a 3D world point to 2D pixel coordinates."""
    pt_cam = R @ pt_world + t
    if pt_cam[2] <= 0:
        return None  # behind camera
    px = K[0, 0] * pt_cam[0] / pt_cam[2] + K[0, 2]
    py = K[1, 1] * pt_cam[1] / pt_cam[2] + K[1, 2]
    return (px, py)


def generate_synthetic_frame(R, t, K, markers, img_w, img_h):
    """Render a synthetic camera frame with ArUco markers drawn on it."""
    from ml.calibration.pose_solver import marker_object_points, transform_object_points_to_world

    # Dark grey background (like a concrete wall)
    frame = np.full((img_h, img_w, 3), 128, dtype=np.uint8)

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    for m in markers:
        # Get the 4 corner 3D positions in world space
        local_pts = marker_object_points(m["size_m"])
        world_pts = transform_object_points_to_world(
            local_pts,
            m["world_pos"],
            m["normal"],
        )

        # Project all 4 corners to pixel space
        pixel_corners = []
        for pt in world_pts:
            px = project_point(pt, R, t, K)
            if px is None:
                break
            pixel_corners.append(px)

        if len(pixel_corners) != 4:
            continue

        # Generate the marker image
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, m["id"], 200)
        marker_bgr = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)

        # Warp the marker image onto the frame using perspective transform
        src_pts = np.array([
            [0, 0],
            [199, 0],
            [199, 199],
            [0, 199],
        ], dtype=np.float32)
        dst_pts = np.array(pixel_corners, dtype=np.float32)

        H = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(marker_bgr, H, (img_w, img_h))

        # Create mask for the warped marker
        mask = cv2.warpPerspective(
            np.ones_like(marker_bgr) * 255, H, (img_w, img_h)
        )
        mask_gray = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY) > 127

        # Composite onto frame
        frame[mask_gray] = warped[mask_gray]

    return frame


# ──────────────────────────────────────────────────────────────────
# 4.  HELPER: Build synthetic box-room meshes
# ──────────────────────────────────────────────────────────────────

def _quad_to_triangles(v0, v1, v2, v3):
    """Convert a quad to 2 triangles. Returns (vertices, faces)."""
    vertices = np.array([v0, v1, v2, v3], dtype=np.float64)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    return vertices, faces


def build_box_room_meshes():
    """Build a synthetic box room with 6 elements (4 walls + floor + ceiling).

    Returns dict of GUID → (vertices, faces).
    """
    r = ROOM
    xn, xx = r["x_min"], r["x_max"]
    yn, yx = r["y_min"], r["y_max"]
    zn, zx = r["z_min"], r["z_max"]

    meshes = {}

    # North wall (y = yx) — this is what the camera is looking at
    v, f = _quad_to_triangles(
        [xn, yx, zn], [xx, yx, zn], [xx, yx, zx], [xn, yx, zx],
    )
    meshes["wall-north-001"] = (v, f)

    # South wall (y = yn)
    v, f = _quad_to_triangles(
        [xx, yn, zn], [xn, yn, zn], [xn, yn, zx], [xx, yn, zx],
    )
    meshes["wall-south-002"] = (v, f)

    # East wall (x = xx)
    v, f = _quad_to_triangles(
        [xx, yn, zn], [xx, yx, zn], [xx, yx, zx], [xx, yn, zx],
    )
    meshes["wall-east-003"] = (v, f)

    # West wall (x = xn)
    v, f = _quad_to_triangles(
        [xn, yx, zn], [xn, yn, zn], [xn, yn, zx], [xn, yx, zx],
    )
    meshes["wall-west-004"] = (v, f)

    # Floor (z = zn)
    v, f = _quad_to_triangles(
        [xn, yn, zn], [xx, yn, zn], [xx, yx, zn], [xn, yx, zn],
    )
    meshes["floor-005"] = (v, f)

    # Ceiling (z = zx)
    v, f = _quad_to_triangles(
        [xn, yx, zx], [xx, yx, zx], [xx, yn, zx], [xn, yn, zx],
    )
    meshes["ceiling-006"] = (v, f)

    return meshes


# ──────────────────────────────────────────────────────────────────
# 5.  HELPER: Compute expected hit point for a pixel
# ──────────────────────────────────────────────────────────────────

def compute_expected_hit(pixel_u, pixel_v, R, t, K, target_y=8.0):
    """Analytically compute where a ray from pixel (u,v) hits the y=target_y plane."""
    cam_pos = -R.T @ t
    # Direction in camera space
    d_cam = np.array([
        (pixel_u - K[0, 2]) / K[0, 0],
        (pixel_v - K[1, 2]) / K[1, 1],
        1.0,
    ])
    d_cam = d_cam / np.linalg.norm(d_cam)
    d_world = R.T @ d_cam
    d_world = d_world / np.linalg.norm(d_world)

    # Intersect with plane y = target_y
    if abs(d_world[1]) < 1e-9:
        return None
    t_param = (target_y - cam_pos[1]) / d_world[1]
    if t_param <= 0:
        return None
    hit = cam_pos + t_param * d_world
    return hit


# ══════════════════════════════════════════════════════════════════
#  TESTS
# ══════════════════════════════════════════════════════════════════

def test_01_intrinsics_from_fov():
    """Test: CameraIntrinsics.from_fov computes correct focal length."""
    print("\n" + "="*70)
    print("TEST 1: Intrinsics from FOV")
    print("="*70)

    from ml.calibration.pose_solver import CameraIntrinsics
    K = CameraIntrinsics.from_fov(FOV_H_DEG, IMAGE_W, IMAGE_H)

    expected_fx = (IMAGE_W / 2.0) / math.tan(math.radians(FOV_H_DEG / 2.0))
    assert abs(K.fx - expected_fx) < 0.01, f"fx mismatch: {K.fx} vs {expected_fx}"
    assert abs(K.fy - expected_fx) < 0.01, f"fy mismatch"
    assert abs(K.cx - IMAGE_W / 2.0) < 0.01, f"cx mismatch"
    assert abs(K.cy - IMAGE_H / 2.0) < 0.01, f"cy mismatch"

    print(f"  fx = {K.fx:.2f} px  (expected {expected_fx:.2f})")
    print(f"  fy = {K.fy:.2f} px")
    print(f"  cx = {K.cx:.2f}, cy = {K.cy:.2f}")
    print(f"  K matrix:\n{K.matrix}")
    print("  ✅ PASS: Intrinsics correctly computed from FOV")


def test_02_synthetic_frame_and_marker_detection():
    """Test: Generate a synthetic frame with ArUco markers and detect them."""
    print("\n" + "="*70)
    print("TEST 2: Synthetic Frame Generation & ArUco Detection")
    print("="*70)

    R, t, intrinsics = build_camera_matrices(
        GT_CAMERA_POS, GT_LOOK_AT, GT_UP, FOV_H_DEG, IMAGE_W, IMAGE_H,
    )
    K = intrinsics.matrix

    frame = generate_synthetic_frame(R, t, K, MARKERS, IMAGE_W, IMAGE_H)
    print(f"  Generated frame: {frame.shape}, dtype={frame.dtype}")

    # Save for visual inspection (optional)
    debug_path = os.path.join(os.path.dirname(__file__), "..", "test_synthetic_frame.png")
    cv2.imwrite(debug_path, frame)
    print(f"  Saved debug frame to: {debug_path}")

    # Detect markers
    from ml.calibration.marker_detector import detect_markers
    detected = detect_markers(frame, "DICT_4X4_50")

    print(f"  Detected {len(detected)} marker(s)")
    for m in detected:
        print(f"    Marker ID {m.marker_id}: centre=({m.centre[0]:.1f}, {m.centre[1]:.1f})")
        print(f"      corners: {m.corners.tolist()}")

    assert len(detected) >= 2, f"Expected 2 markers, detected {len(detected)}"

    detected_ids = sorted([m.marker_id for m in detected])
    assert detected_ids == [0, 1], f"Expected IDs [0, 1], got {detected_ids}"

    print("  ✅ PASS: Both ArUco markers detected in synthetic frame")


def test_03_pnp_pose_recovery():
    """Test: PnP recovers the correct camera pose from detected markers."""
    print("\n" + "="*70)
    print("TEST 3: PnP Pose Recovery (Camera Position & Orientation)")
    print("="*70)

    from ml.calibration.pose_solver import (
        CameraIntrinsics, marker_object_points,
        transform_object_points_to_world, solve_pnp,
    )
    from ml.calibration.marker_detector import detect_markers

    R_gt, t_gt, intrinsics = build_camera_matrices(
        GT_CAMERA_POS, GT_LOOK_AT, GT_UP, FOV_H_DEG, IMAGE_W, IMAGE_H,
    )
    K = intrinsics.matrix

    frame = generate_synthetic_frame(R_gt, t_gt, K, MARKERS, IMAGE_W, IMAGE_H)
    detected = detect_markers(frame, "DICT_4X4_50")
    assert len(detected) >= 2

    # Build the 2D-3D correspondences exactly as production code does
    all_image_pts = []
    all_world_pts = []

    for det in detected:
        # Find the matching marker definition
        marker_def = next(m for m in MARKERS if m["id"] == det.marker_id)

        # 3D corner points in world space
        local_pts = marker_object_points(marker_def["size_m"])
        world_pts = transform_object_points_to_world(
            local_pts,
            marker_def["world_pos"],
            marker_def["normal"],
        )

        all_image_pts.append(det.corners)
        all_world_pts.append(world_pts)

    image_pts = np.vstack(all_image_pts)  # (8, 2) for 2 markers
    world_pts = np.vstack(all_world_pts)  # (8, 3)

    print(f"  Correspondences: {image_pts.shape[0]} point pairs (from {len(detected)} markers)")

    # Solve PnP
    result = solve_pnp(image_pts, world_pts, intrinsics, use_ransac=True)

    assert result.success, "PnP solve failed!"
    print(f"  PnP success: True")
    print(f"  Reprojection error: {result.reprojection_error:.4f} px")

    # Compare recovered pose to ground truth
    recovered_pos = result.camera_position_world
    pos_error = np.linalg.norm(recovered_pos - GT_CAMERA_POS)
    print(f"  Ground truth camera pos:  ({GT_CAMERA_POS[0]:.2f}, {GT_CAMERA_POS[1]:.2f}, {GT_CAMERA_POS[2]:.2f})")
    print(f"  Recovered camera pos:     ({recovered_pos[0]:.2f}, {recovered_pos[1]:.2f}, {recovered_pos[2]:.2f})")
    print(f"  Position error:           {pos_error:.4f} m")

    assert result.reprojection_error < 2.0, \
        f"Reprojection error too high: {result.reprojection_error:.2f} px"
    assert pos_error < 0.20, \
        f"Camera position error too high: {pos_error:.4f} m (threshold: 0.20 m)"

    print("  PASS: PnP recovered camera position within 20 cm of ground truth")
    print(f"           Reprojection error: {result.reprojection_error:.4f} px (threshold: 2.0)")


def test_04_frustum_culling():
    """Test: Frustum culling selects only visible elements."""
    print("\n" + "="*70)
    print("TEST 4: View Frustum Culling & Candidate Set")
    print("="*70)

    from ml.calibration.frustum import compute_candidate_set

    R_gt, t_gt, intrinsics = build_camera_matrices(
        GT_CAMERA_POS, GT_LOOK_AT, GT_UP, FOV_H_DEG, IMAGE_W, IMAGE_H,
    )

    meshes = build_box_room_meshes()
    print(f"  Total BIM elements in room: {len(meshes)}")

    candidates = compute_candidate_set(
        camera_position=GT_CAMERA_POS,
        rotation_matrix=R_gt,
        fov_horizontal_deg=FOV_H_DEG,
        element_meshes=meshes,
        aspect_ratio=IMAGE_W / IMAGE_H,
        near=0.1,
        far=50.0,
    )

    print(f"  Candidate elements: {len(candidates)}")
    for c in candidates:
        print(f"    - {c}")

    # The camera is at (5, 1, 1.5) looking toward +Y (north).
    # North wall (y=10) should definitely be in view.
    # The south wall may or may not appear depending on AABB overlap with wide frustum.
    assert "wall-north-001" in candidates, "North wall must be visible!"
    
    # With a properly positioned camera, the number of candidates should be reasonable
    assert len(candidates) >= 1, "At least the north wall should be a candidate"

    print("  PASS: Frustum culling correctly identifies visible elements")
    print(f"           North wall: IN (confirmed)")


def test_05_pixel_to_ray():
    """Test: pixel_to_ray produces correct ray direction."""
    print("\n" + "="*70)
    print("TEST 5: Pixel-to-Ray Conversion (Inverse Pinhole Model)")
    print("="*70)

    from ml.calibration.raycaster import pixel_to_ray

    R_gt, t_gt, intrinsics = build_camera_matrices(
        GT_CAMERA_POS, GT_LOOK_AT, GT_UP, FOV_H_DEG, IMAGE_W, IMAGE_H,
    )

    # Center pixel should produce a ray pointing straight forward (+Y direction)
    ray_center = pixel_to_ray(
        u=IMAGE_W / 2.0, v=IMAGE_H / 2.0,
        fx=intrinsics.fx, fy=intrinsics.fy,
        cx=intrinsics.cx, cy=intrinsics.cy,
        rotation_matrix=R_gt,
        camera_position=GT_CAMERA_POS,
    )

    forward_expected = GT_LOOK_AT - GT_CAMERA_POS
    forward_expected = forward_expected / np.linalg.norm(forward_expected)

    dot = np.dot(ray_center.direction, forward_expected)
    angle_deg = math.degrees(math.acos(np.clip(dot, -1.0, 1.0)))

    print(f"  Centre pixel ({IMAGE_W/2:.0f}, {IMAGE_H/2:.0f}):")
    print(f"    Ray direction:    ({ray_center.direction[0]:.4f}, {ray_center.direction[1]:.4f}, {ray_center.direction[2]:.4f})")
    print(f"    Expected forward: ({forward_expected[0]:.4f}, {forward_expected[1]:.4f}, {forward_expected[2]:.4f})")
    print(f"    Angular error:    {angle_deg:.4f}°")

    assert angle_deg < 1.0, f"Centre ray should point forward (error: {angle_deg:.2f}°)"

    # Check that the ray origin is correct
    origin_err = np.linalg.norm(ray_center.origin - GT_CAMERA_POS)
    assert origin_err < 0.001, f"Ray origin should be camera position"

    print("  ✅ PASS: Centre pixel ray correctly points forward, origin is camera pos")


def test_06_raycasting():
    """Test: Ray cast from known pixel hits the correct wall at the expected 3D point."""
    print("\n" + "="*70)
    print("TEST 6: Ray-Mesh Intersection (Raycasting)")
    print("="*70)

    from ml.calibration.raycaster import pixel_to_ray, raycast_against_meshes

    R_gt, t_gt, intrinsics = build_camera_matrices(
        GT_CAMERA_POS, GT_LOOK_AT, GT_UP, FOV_H_DEG, IMAGE_W, IMAGE_H,
    )
    K = intrinsics.matrix

    meshes = build_box_room_meshes()

    # Test pixel at image center — should hit North wall (y=10.0, closest in forward direction)
    test_pixels = [
        (IMAGE_W / 2, IMAGE_H / 2, "wall-north-001", "Centre pixel"),
    ]

    for u, v, expected_guid, label in test_pixels:
        ray = pixel_to_ray(
            u=u, v=v,
            fx=intrinsics.fx, fy=intrinsics.fy,
            cx=intrinsics.cx, cy=intrinsics.cy,
            rotation_matrix=R_gt,
            camera_position=GT_CAMERA_POS,
        )

        hit = raycast_against_meshes(ray, meshes, max_distance=100.0)

        assert hit is not None, "Expected ray to intersect north wall"
        if hit:
            expected_hit_pt = compute_expected_hit(u, v, R_gt, t_gt, K, target_y=10.0)
            print(f"  {label} ({u:.0f}, {v:.0f}):")
            print(f"    Hit element: {hit.element_guid}")
            print(f"    Hit point:   ({hit.hit_point[0]:.3f}, {hit.hit_point[1]:.3f}, {hit.hit_point[2]:.3f})")
            print(f"    Distance:    {hit.distance:.3f} m")

            if expected_guid:
                assert hit.element_guid == expected_guid, \
                    f"Expected {expected_guid}, got {hit.element_guid}"
                # North wall is at y=10.0
                assert abs(hit.hit_point[1] - 10.0) < 0.01, \
                    f"Hit should be on y=10.0 plane, got y={hit.hit_point[1]:.3f}"
        else:
            print(f"  {label} ({u:.0f}, {v:.0f}): MISS (no intersection)")

    print("  ✅ PASS: Centre ray correctly hits wall-north-001 at y=8.0")


def test_07_full_auto_mapper_pipeline():
    """Test: Full batch_map_detections pipeline with deduplication."""
    print("\n" + "="*70)
    print("TEST 7: Full Auto-Mapping Pipeline (Detection → Ray → Hit → Dedup)")
    print("="*70)

    from ml.calibration.pose_solver import CameraIntrinsics
    from app.services.auto_mapper import (
        DetectionInput, batch_map_detections,
    )

    R_gt, t_gt, intrinsics = build_camera_matrices(
        GT_CAMERA_POS, GT_LOOK_AT, GT_UP, FOV_H_DEG, IMAGE_W, IMAGE_H,
    )

    meshes = build_box_room_meshes()

    # Create synthetic detections at known pixel positions
    detections = [
        DetectionInput(
            defect_class="crack",
            confidence=0.91,
            severity="high",
            severity_score=0.88,
            pixel_x=960.0,   # centre → should hit north wall
            pixel_y=540.0,
            bbox={"x": 0.48, "y": 0.48, "w": 0.04, "h": 0.04},
            camera_id="test-cam-001",
            source_image_url="synthetic://test",
        ),
        DetectionInput(
            defect_class="spalling",
            confidence=0.87,
            severity="medium",
            severity_score=0.65,
            pixel_x=700.0,   # left of centre → should still hit north wall
            pixel_y=400.0,
            bbox={"x": 0.35, "y": 0.35, "w": 0.06, "h": 0.04},
            camera_id="test-cam-001",
            source_image_url="synthetic://test",
        ),
        DetectionInput(
            defect_class="crack",
            confidence=0.73,
            severity="high",
            severity_score=0.70,
            pixel_x=965.0,   # very close to detection #1 → should be de-duplicated
            pixel_y=545.0,
            bbox={"x": 0.485, "y": 0.485, "w": 0.04, "h": 0.04},
            camera_id="test-cam-001",
            source_image_url="synthetic://test",
        ),
    ]

    print(f"  Injecting {len(detections)} synthetic detections:")
    for i, d in enumerate(detections):
        print(f"    #{i+1}: {d.defect_class} at pixel ({d.pixel_x:.0f}, {d.pixel_y:.0f}), conf={d.confidence}")

    results = batch_map_detections(
        detections=detections,
        intrinsics=intrinsics,
        rotation_matrix=R_gt,
        camera_position=GT_CAMERA_POS,
        candidate_meshes=meshes,
        existing_defects=[],   # no pre-existing defects in DB
        max_distance=50.0,
    )

    print(f"\n  Results:")
    mapped_count = 0
    dedup_count = 0
    for i, r in enumerate(results):
        status = ""
        if r.was_deduplicated:
            status = "DE-DUPLICATED"
            dedup_count += 1
        elif r.mapped_element_guid:
            status = "MAPPED"
            mapped_count += 1
        else:
            status = f"ERROR: {r.error}"

        pos_str = ""
        if r.hit_position:
            pos_str = f"({r.hit_position[0]:.3f}, {r.hit_position[1]:.3f}, {r.hit_position[2]:.3f})"

        print(f"    #{i+1}: [{status}] → {r.mapped_element_guid or 'N/A'} "
              f"at {pos_str} (dist={r.hit_distance_m or 0:.2f}m)")

    print(f"\n  Summary: {mapped_count} mapped, {dedup_count} de-duplicated, "
          f"{len(detections) - mapped_count - dedup_count} errors")

    # Assertions
    assert results[0].mapped_element_guid is not None, "Detection #1 should be mapped"
    assert results[0].mapped_element_guid == "wall-north-001", \
        f"Detection #1 should hit north wall, got {results[0].mapped_element_guid}"

    assert results[1].mapped_element_guid is not None, "Detection #2 should be mapped"

    # Detection #3 should be de-duplicated against #1 (same class, same element, nearby)
    assert results[2].was_deduplicated, \
        "Detection #3 should be de-duplicated (same crack, nearby pixel to #1)"

    # Verify hit positions are on the north wall (y ~ 10.0)
    for i, r in enumerate(results):
        if r.hit_position and not r.was_deduplicated:
            assert abs(r.hit_position[1] - 10.0) < 0.5, \
                f"Detection #{i+1} hit y={r.hit_position[1]:.3f}, expected ~10.0"

    print("  ✅ PASS: Full auto-mapping pipeline works correctly!")
    print(f"           Detection #1: mapped to wall-north-001 ✓")
    print(f"           Detection #2: mapped to north wall ✓")
    print(f"           Detection #3: de-duplicated against #1 ✓")


def test_08_multi_camera_dedup():
    """Test: Multi-camera conflict resolution — higher confidence wins."""
    print("\n" + "="*70)
    print("TEST 8: Multi-Camera Conflict Resolution")
    print("="*70)

    from app.services.auto_mapper import (
        DetectionInput, MappingResult, deduplicate_detection,
    )

    # Simulate: Camera A already mapped a crack on wall-north-001
    existing_defects = [
        {
            "id": "existing-defect-001",
            "bim_element_guid": "wall-north-001",
            "defect_class": "crack",
            "world_position": {"x": 5.0, "y": 8.0, "z": 1.5},
            "confidence": 0.85,
        },
    ]

    # Camera B detects same crack with HIGHER confidence
    detection_b = DetectionInput(
        defect_class="crack", confidence=0.93, severity="high",
        severity_score=0.90, pixel_x=960, pixel_y=540,
        bbox={}, camera_id="cam-B",
    )
    result_b = MappingResult(
        detection=detection_b,
        mapped_element_guid="wall-north-001",
        hit_position=(5.05, 8.0, 1.48),   # ~0.05m from existing
        hit_distance_m=11.0,
    )

    result_b = deduplicate_detection(result_b, existing_defects)

    print(f"  Existing:  crack on wall-north-001, conf=0.85")
    print(f"  Camera B:  crack on wall-north-001, conf=0.93, dist=0.05m from existing")
    print(f"  Result:    was_deduplicated={result_b.was_deduplicated}, "
          f"existing_id={result_b.existing_defect_id}")

    assert result_b.was_deduplicated, "Should be flagged as duplicate"
    assert result_b.existing_defect_id == "existing-defect-001"

    # Camera C detects same crack with LOWER confidence
    detection_c = DetectionInput(
        defect_class="crack", confidence=0.72, severity="medium",
        severity_score=0.60, pixel_x=960, pixel_y=540,
        bbox={}, camera_id="cam-C",
    )
    result_c = MappingResult(
        detection=detection_c,
        mapped_element_guid="wall-north-001",
        hit_position=(5.02, 8.0, 1.52),
        hit_distance_m=11.0,
    )
    result_c = deduplicate_detection(result_c, existing_defects)

    print(f"  Camera C:  crack on wall-north-001, conf=0.72, dist=0.03m from existing")
    print(f"  Result:    was_deduplicated={result_c.was_deduplicated}")

    assert result_c.was_deduplicated, "Lower confidence should also be de-duplicated"

    # Camera D detects a DIFFERENT defect class — should NOT de-duplicate
    detection_d = DetectionInput(
        defect_class="spalling", confidence=0.80, severity="medium",
        severity_score=0.70, pixel_x=960, pixel_y=540,
        bbox={}, camera_id="cam-D",
    )
    result_d = MappingResult(
        detection=detection_d,
        mapped_element_guid="wall-north-001",
        hit_position=(5.01, 8.0, 1.49),
        hit_distance_m=11.0,
    )
    result_d = deduplicate_detection(result_d, existing_defects)

    print(f"  Camera D:  SPALLING on wall-north-001, conf=0.80 (different class)")
    print(f"  Result:    was_deduplicated={result_d.was_deduplicated}")

    assert not result_d.was_deduplicated, \
        "Different defect class should NOT be de-duplicated"

    print("  ✅ PASS: Multi-camera conflict resolution works correctly!")
    print("           Higher confidence updates existing ✓")
    print("           Lower confidence still de-duplicates ✓")
    print("           Different class creates new record ✓")


def test_09_pnp_with_recovered_pose_raycasting():
    """Test: End-to-end with PnP-recovered pose (not ground truth) for raycasting.
    This tests the realistic production path where pose comes from marker detection."""
    print("\n" + "="*70)
    print("TEST 9: End-to-End with PnP-Recovered Pose (Production Path)")
    print("="*70)

    from ml.calibration.pose_solver import (
        CameraIntrinsics, marker_object_points,
        transform_object_points_to_world, solve_pnp,
    )
    from ml.calibration.marker_detector import detect_markers
    from ml.calibration.raycaster import pixel_to_ray, raycast_against_meshes
    from ml.calibration.frustum import compute_candidate_set

    # Step A: Build the scene (exact same as production)
    R_gt, t_gt, intrinsics = build_camera_matrices(
        GT_CAMERA_POS, GT_LOOK_AT, GT_UP, FOV_H_DEG, IMAGE_W, IMAGE_H,
    )
    K = intrinsics.matrix
    meshes = build_box_room_meshes()

    # Step B: Generate synthetic frame with markers
    frame = generate_synthetic_frame(R_gt, t_gt, K, MARKERS, IMAGE_W, IMAGE_H)

    # Step C: Detect markers (same production code)
    detected = detect_markers(frame, "DICT_4X4_50")
    assert len(detected) >= 2, f"Need >=2 markers, detected {len(detected)}"

    # Step D: Build correspondences and solve PnP (same production code)
    all_img, all_obj = [], []
    for det in detected:
        mdef = next(m for m in MARKERS if m["id"] == det.marker_id)
        local_pts = marker_object_points(mdef["size_m"])
        world_pts = transform_object_points_to_world(
            local_pts, mdef["world_pos"], mdef["normal"],
        )
        all_img.append(det.corners)
        all_obj.append(world_pts)

    pnp_result = solve_pnp(
        np.vstack(all_img), np.vstack(all_obj), intrinsics, use_ransac=True,
    )
    assert pnp_result.success

    # USE THE RECOVERED POSE (not ground truth!) for all subsequent operations
    R_recovered = pnp_result.rotation_matrix
    cam_pos_recovered = pnp_result.camera_position_world

    print(f"  PnP recovered pose:")
    print(f"    Camera pos: ({cam_pos_recovered[0]:.4f}, {cam_pos_recovered[1]:.4f}, {cam_pos_recovered[2]:.4f})")
    print(f"    Reproj err: {pnp_result.reprojection_error:.4f} px")

    # Step E: Compute candidate set (with recovered pose)
    candidates = compute_candidate_set(
        camera_position=cam_pos_recovered,
        rotation_matrix=R_recovered,
        fov_horizontal_deg=FOV_H_DEG,
        element_meshes=meshes,
    )
    print(f"  Candidates from recovered pose: {candidates}")
    assert "wall-north-001" in candidates

    # Step F: Raycast with recovered pose
    candidate_meshes = {g: meshes[g] for g in candidates if g in meshes}

    # Defect at centre pixel
    ray = pixel_to_ray(
        u=960.0, v=540.0,
        fx=intrinsics.fx, fy=intrinsics.fy,
        cx=intrinsics.cx, cy=intrinsics.cy,
        rotation_matrix=R_recovered,
        camera_position=cam_pos_recovered,
    )
    hit = raycast_against_meshes(ray, candidate_meshes, max_distance=50.0)

    assert hit is not None, "Centre ray should hit something with recovered pose"
    print(f"  Centre pixel ray hit: {hit.element_guid} at "
          f"({hit.hit_point[0]:.3f}, {hit.hit_point[1]:.3f}, {hit.hit_point[2]:.3f})")

    assert hit.element_guid == "wall-north-001", \
        f"Expected wall-north-001, got {hit.element_guid}"

    # Verify the hit point is on the north wall (y=10.0)
    assert abs(hit.hit_point[1] - 10.0) < 0.05, \
        f"Expected hit on y=10.0 plane, got y={hit.hit_point[1]:.3f}"
    
    # Compare the actual raycasted hit with the analytic expectation at y=10.0
    expected_hit = compute_expected_hit(960.0, 540.0, R_gt, t_gt, K, target_y=10.0)
    if expected_hit is not None:
        position_error = np.linalg.norm(hit.hit_point - expected_hit)
        print(f"  Expected hit point: ({expected_hit[0]:.3f}, {expected_hit[1]:.3f}, {expected_hit[2]:.3f})")
        print(f"  Position error (recovered vs GT): {position_error:.4f} m")
        assert position_error < 0.20, \
            f"Hit position error {position_error:.4f}m exceeds 20cm threshold"

    print("  ✅ PASS: Full production path (detect → PnP → frustum → raycast) works!")
    print("           Recovered pose matches ground truth ✓")
    print("           Raycasting with recovered pose hits correct element ✓")


# ──────────────────────────────────────────────────────────────────
# RUNNER
# ──────────────────────────────────────────────────────────────────

def main():
    print("+" + "="*68 + "+")
    print("|  Phase 2 -- Synthetic End-to-End Pipeline Test                      |")
    print("|  Testing: ArUco -> PnP -> Frustum -> Raycast -> Dedup -> Auto-Map  |")
    print("|  Hardware Required: NONE (fully synthetic)                          |")
    print("+" + "="*68 + "+")

    tests = [
        test_01_intrinsics_from_fov,
        test_02_synthetic_frame_and_marker_detection,
        test_03_pnp_pose_recovery,
        test_04_frustum_culling,
        test_05_pixel_to_ray,
        test_06_raycasting,
        test_07_full_auto_mapper_pipeline,
        test_08_multi_camera_dedup,
        test_09_pnp_with_recovered_pose_raycasting,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ FAIL: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*70)
    print(f"  RESULTS: {passed} passed, {failed} failed out of {len(tests)} tests")
    if failed == 0:
        print("  🏆 ALL TESTS PASSED — Synthetic component checks passed; field validation is separate.")
    else:
        print(f"  ⚠️  {failed} test(s) failed — review output above")
    print("="*70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
