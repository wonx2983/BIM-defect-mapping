"""Offline evidence run using an IFC, virtual camera and the production detector/mapper."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath

import cv2
import ifcopenshell
import numpy as np
import torch
from PIL import Image

from app.services.auto_mapper import DetectionInput, map_detection_to_element
from ml.calibration.camera_calibrator import calibrate_camera_from_frame
from ml.calibration.ifc_geometry import extract_meshes_from_ifc
from ml.calibration.marker_detector import detect_markers
from ml.calibration.pose_solver import (
    CameraIntrinsics, marker_object_points, transform_object_points_to_world,
)
from ml.inference.detector import DefectDetector

WIDTH, HEIGHT, FOV = 1280, 720, 57.0
DICTIONARY = "DICT_4X4_50"
MARKER_ID = 17


def unit(vector):
    return vector / np.linalg.norm(vector)


def camera_rotation(position, target):
    forward = unit(target - position)
    right = unit(np.cross(forward, [0, 0, 1]))
    return np.array([right, np.cross(forward, right), forward])


def project(points, position, rotation, intrinsics):
    local = (points - position) @ rotation.T
    return local[..., :2] / local[..., 2, None] * [intrinsics.fx, intrinsics.fy] + [
        intrinsics.cx, intrinsics.cy
    ]


def render(triangles, owners, types, position, rotation, intrinsics):
    """Perspective rasterization. The depth buffer supplies independent ground truth."""
    local = (triangles - position) @ rotation.T
    depths = local[:, :, 2]
    valid = np.flatnonzero(np.all(depths > 0.2, axis=1))
    projected = project(triangles[valid], position, rotation, intrinsics)
    visible = np.full((HEIGHT, WIDTH), -1, np.int32)
    depth = np.full((HEIGHT, WIDTH), np.inf)
    frame = np.full((HEIGHT, WIDTH, 3), (206, 221, 230), np.uint8)
    colours = {"IfcWall": (153, 166, 180), "IfcWallStandardCase": (153, 166, 180),
               "IfcSlab": (174, 178, 183), "IfcColumn": (180, 188, 194)}
    for index, points in zip(valid, projected):
        x0, y0 = np.maximum(np.floor(points.min(axis=0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(points.max(axis=0)).astype(int) + 1, [WIDTH, HEIGHT])
        if x0 >= x1 or y0 >= y1:
            continue
        a, b, c = points
        ab, ac = b - a, c - a
        denominator = ab[0] * ac[1] - ab[1] * ac[0]
        if abs(denominator) < 1e-8:
            continue
        y, x = np.ogrid[y0:y1, x0:x1]
        s = ((x - a[0]) * ac[1] - (y - a[1]) * ac[0]) / denominator
        t = (ab[0] * (y - a[1]) - ab[1] * (x - a[0])) / denominator
        z = 1 / np.maximum((1 - s - t) / depths[index, 0] + s / depths[index, 1] + t / depths[index, 2], 1e-9)
        region = np.s_[y0:y1, x0:x1]
        mask = (s >= -1e-8) & (t >= -1e-8) & (s + t <= 1 + 1e-8) & (z < depth[region])
        if not mask.any():
            continue
        depth[region][mask] = z[mask]
        visible[region][mask] = index
        tri = triangles[index]
        normal = unit(np.cross(tri[1] - tri[0], tri[2] - tri[0]))
        shading = 0.77 + 0.23 * abs(normal @ unit(np.array([0.4, -0.5, 1.])))
        frame[region][mask] = np.asarray(colours.get(types[owners[index]], (169, 179, 184))) * shading
    rng = np.random.default_rng(1234)
    grain = rng.normal(0, 2.8, (HEIGHT, WIDTH, 1)) * (visible >= 0)[..., None]
    return np.clip(frame + grain, 0, 255).astype(np.uint8), visible, depth


def surface_point(pixel, depth, position, rotation, intrinsics):
    x, y = pixel
    local = np.array([(x - intrinsics.cx) / intrinsics.fx,
                      (y - intrinsics.cy) / intrinsics.fy, 1.0]) * depth[y, x]
    return position + rotation.T @ local


def clearance(mask):
    mask = mask.astype(np.uint8)
    mask[:45] = mask[-45:] = 0
    mask[:, :45] = mask[:, -45:] = 0
    return cv2.distanceTransform(mask, cv2.DIST_L2, 5)


def place_marker(frame, visible, depth, triangles, triangle_owners, types,
                 position, rotation, intrinsics):
    owner_image = np.where(visible >= 0, triangle_owners[visible], -1)
    ranks = []
    for owner in np.unique(owner_image):
        if owner < 0 or not types[owner].startswith("IfcWall"):
            continue
        distance = clearance(owner_image == owner)
        _, radius, _, pixel = cv2.minMaxLoc(distance)
        ranks.append((radius, owner, pixel))
    for radius, owner, pixel in sorted(ranks, reverse=True):
        if radius < 38:
            break
        x, y = pixel
        world = surface_point(pixel, depth, position, rotation, intrinsics)
        a, b, c = triangles[visible[y, x]]
        normal = unit(np.cross(b - a, c - a))
        if normal @ (position - world) < 0:
            normal = -normal
        side = min(120, radius * 1.17) * depth[y, x] / intrinsics.fx
        border = transform_object_points_to_world(marker_object_points(side * 4 / 3), world, normal)
        corners = project(border, position, rotation, intrinsics).astype(np.float32)
        polygon = np.zeros_like(visible, dtype=np.uint8)
        cv2.fillConvexPoly(polygon, np.rint(corners).astype(np.int32), 1)
        if np.any(owner_image[polygon > 0] != owner):
            continue
        yy, xx = np.where(polygon > 0)
        if len(xx) == 0:
            continue
        raster_points = position + (
            np.column_stack([(xx - intrinsics.cx) / intrinsics.fx,
                             (yy - intrinsics.cy) / intrinsics.fy, np.ones(len(xx))])
            * depth[yy, xx, None]
        ) @ rotation
        if np.max(np.abs((raster_points - world) @ normal)) > .012:
            continue
        pattern = np.full((256, 256), 255, np.uint8)
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        pattern[32:224, 32:224] = cv2.aruco.generateImageMarker(dictionary, MARKER_ID, 192)
        warp = cv2.getPerspectiveTransform(np.float32([[0, 0], [256, 0], [256, 256], [0, 256]]), corners)
        stamp = cv2.warpPerspective(pattern, warp, (WIDTH, HEIGHT), flags=cv2.INTER_LINEAR)
        image = frame.copy()
        image[polygon > 0] = stamp[polygon > 0, None]
        if not detect_markers(image, DICTIONARY):
            continue
        registry = dict(id="simulated-marker-17", marker_dict_id=MARKER_ID,
                        aruco_dict_type=DICTIONARY, physical_size_m=float(side), rotation_deg=0)
        registry.update({f"world_{axis}": float(value) for axis, value in zip("xyz", world)})
        registry.update({f"normal_{axis}": float(value) for axis, value in zip("xyz", normal)})
        return image, registry, owner_image, polygon
    return None


def draw_crack(frame, pixel, seed, radius):
    """Render a seeded branching hairline with a dark interior and chipped edges."""
    rng = np.random.default_rng(seed)
    x, y = pixel
    length = min(66, int(radius * 1.25))
    dx = np.linspace(-length / 2, length / 2, 27)
    dy = 0.52 * dx + np.cumsum(rng.normal(0, 2.6, len(dx)))
    dy -= (dy.min() + dy.max()) / 2
    points = np.rint(np.column_stack([x + dx, y + dy])).astype(np.int32)
    mask = np.zeros(frame.shape[:2], np.uint8)
    for index in range(len(points) - 1):
        cv2.line(mask, points[index], points[index + 1], 210, 1 + (index % 4 == 0), cv2.LINE_AA)
    for index in (7, 14, 19):
        start = points[index]
        end = start + np.array([rng.integers(-10, 11), rng.choice([-1, 1]) * rng.integers(7, 15)])
        cv2.line(mask, start, end, 165, 1, cv2.LINE_AA)
    frame[:] = (frame * (1 - (mask[..., None] / 255) * 0.86)).astype(np.uint8)
    yy, xx = np.where(mask > 16)
    return [int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1]


def centre(box):
    return [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]


def overlap(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = lambda box: (box[2] - box[0]) * (box[3] - box[1])
    return intersection / (area(a) + area(b) - intersection)


def annotate(frame, rows, colour, label):
    image = frame.copy()
    for index, row in enumerate(rows):
        x1, y1, x2, y2 = map(int, row["box"])
        cv2.rectangle(image, (x1, y1), (x2, y2), colour, 2)
        caption = label(index, row)
        (width, height), _ = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, .57, 2)
        origin = (max(3, min(x1, image.shape[1] - width - 4)), max(height + 3, y1 - 7))
        cv2.putText(image, caption, origin, cv2.FONT_HERSHEY_SIMPLEX, .57, colour, 2)
    return image


def combined_overlay(frame, detections):
    return annotate(
        frame, detections, (20, 60, 190),
        lambda index, row: f"D{index + 1}: " + (
            f"{row['matches']} -> correct IFC element" if row.get("correct_element") else
            "wrong IFC element" if row.get("matches") else "unmatched YOLO box"
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ifc", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str((args.out / ".ultralytics").resolve()))
    cv2.setNumThreads(2)
    torch.set_num_threads(4)
    intrinsics = CameraIntrinsics.from_fov(FOV, WIDTH, HEIGHT)
    print("Extracting IFC geometry", flush=True)
    meshes = extract_meshes_from_ifc(args.ifc)
    model = ifcopenshell.open(str(args.ifc))
    guids = list(meshes)
    elements = [model.by_guid(guid) for guid in guids]
    types = [element.is_a() for element in elements]
    triangles = np.concatenate([verts[faces] for verts, faces in meshes.values()])
    owners = np.repeat(np.arange(len(guids)), [len(faces) for _, faces in meshes.values()])
    nondegenerate = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0],
                                           triangles[:, 2] - triangles[:, 0]), axis=1) > 1e-9
    triangles, owners = triangles[nondegenerate], owners[nondegenerate]
    low, high = np.quantile(triangles.reshape(-1, 3), [0.015, 0.985], axis=0)
    target = (low + high) / 2
    target[2] = low[2] + 0.50 * (high[2] - low[2])
    for direction in ([0, -1, 0], [0, 1, 0], [-1, 0, 0], [1, 0, 0]):
        position = target + np.array(direction) * (np.linalg.norm(high[:2] - low[:2]) * 0.84 + 3)
        position[2] -= 0.8
        position[:2] += [2.0 if direction[0] == 0 else 0, 2.0 if direction[1] == 0 else 0]
        rotation = camera_rotation(position, target)
        frame, visible, depth = render(triangles, owners, types, position, rotation, intrinsics)
        placement = place_marker(frame, visible, depth, triangles, owners, types, position, rotation, intrinsics)
        if placement:
            break
    else:
        raise RuntimeError("No visible planar wall could hold a decodable virtual marker")
    clean, registry, owner_image, marker_mask = placement
    print("Virtual marker placed. Calibrating and creating defect cases.", flush=True)
    positive = clean.copy()
    occupied = cv2.dilate(marker_mask, np.ones((55, 55), np.uint8)).astype(bool)
    truth = []
    for family in ("IfcWall", "IfcSlab", "IfcColumn", "IfcWall", "IfcWall"):
        choices = []
        for owner in np.unique(owner_image):
            if owner >= 0 and types[owner].startswith(family):
                distance = clearance((owner_image == owner) & ~occupied)
                _, radius, _, pixel = cv2.minMaxLoc(distance)
                if radius >= 19:
                    choices.append((radius, owner, pixel))
        if not choices:
            continue
        radius, owner, pixel = max(choices)
        box = draw_crack(positive, pixel, 58 + len(truth), radius)
        x, y = map(lambda value: int(round(value)), centre(box))
        if owner_image[y, x] != owner:
            raise RuntimeError("Crack centre crossed a BIM element boundary")
        truth.append(dict(id=f"C{len(truth) + 1}", box=box, element_guid=guids[owner],
                          element_type=types[owner], element_name=elements[owner].Name,
                          pixel=[x, y], world=surface_point((x, y), depth, position, rotation, intrinsics).tolist()))
        cv2.circle(occupied.view(np.uint8), pixel, max(56, int(radius)), 1, -1)
    if not truth:
        raise RuntimeError("No suitable surfaces for test cracks")

    cal = calibrate_camera_from_frame(positive, [registry], fov_horizontal_deg=FOV, ifc_path=args.ifc)
    no_marker = calibrate_camera_from_frame(frame, [registry], fov_horizontal_deg=FOV, ifc_path=args.ifc)
    marker_frame = positive.copy()
    for marker in detect_markers(positive, DICTIONARY):
        polygon = np.rint(marker.corners).astype(np.int32)
        cv2.polylines(marker_frame, [polygon], True, (35, 170, 35), 3)
        cv2.putText(marker_frame, f"ArUco ID {marker.marker_id}", tuple(polygon.min(axis=0) - [0, 8]),
                    cv2.FONT_HERSHEY_SIMPLEX, .7, (10, 80, 10), 2)
    for name, image in (("01-virtual-camera", positive), ("02-clean-control", clean),
                        ("03-ground-truth", annotate(positive, truth, (220, 65, 0), lambda _, row: row["id"])),
                        ("05-marker-calibration", marker_frame), ("07-no-marker-control", frame)):
        if not cv2.imwrite(str(args.out / f"{name}.png"), image):
            raise IOError(f"Could not write {name}")

    weights = Path(__file__).resolve().parent / "ml/models/defect_detector.pt"
    threshold = .25
    detector = DefectDetector(str(weights), device="cpu", confidence_threshold=threshold)
    print("Running YOLO on positive and clean-control frames", flush=True)
    detections = {}
    inference_ms = {}
    for name, image in (("positive", positive), ("clean", clean)):
        result = detector.predict(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)))
        inference_ms[name] = result.inference_time_ms
        rows = []
        for det in result.detections:
            box = [det.bbox_pixels[key] for key in ("x1", "y1", "x2", "y2")]
            rows.append(dict(box=box, defect_class=det.defect_class, confidence=det.confidence,
                             severity=det.severity, severity_score=det.severity_score))
        detections[name] = rows
        cv2.imwrite(str(args.out / f"04-yolo-{name}.png"),
                    annotate(image, rows, (0, 45, 210), lambda i, row: f"D{i+1} {row['defect_class']} {row['confidence']:.2f}"))

    unmatched = set(range(len(truth)))
    for row in sorted(detections["positive"], key=lambda row: -row["confidence"]):
        iou, index = max(((overlap(row["box"], truth[i]["box"]), i) for i in unmatched), default=(0, -1))
        if row["defect_class"] == "crack" and iou >= .5:
            row["matches"] = truth[index]["id"]
            unmatched.remove(index)
        row["best_unmatched_iou"] = iou

    candidates = {guid: meshes[guid] for guid in (cal.candidate_guids or []) if guid in meshes}

    def mapped(pixel, classification, confidence, severity, score, expected=None):
        if not cal.success or not candidates:
            return dict(mapped_guid=None, mapped_world=None, correct_element=False, error_cm=None)
        pose = cal.pnp_result
        item = DetectionInput(defect_class=classification, confidence=confidence, severity=severity,
                              severity_score=score, pixel_x=float(pixel[0]), pixel_y=float(pixel[1]),
                              bbox={}, camera_id="virtual-camera")
        hit = map_detection_to_element(item, cal.intrinsics, pose.rotation_matrix, pose.camera_position_world, candidates)
        point = list(hit.hit_position) if hit.hit_position is not None else None
        return dict(mapped_guid=hit.mapped_element_guid, mapped_world=point, mapping_error=hit.error,
                    correct_element=(hit.mapped_element_guid == expected["element_guid"]) if expected else None,
                    error_cm=float(100 * np.linalg.norm(np.asarray(point) - expected["world"]))
                    if point is not None and expected else None)

    print(f"Mapping {len(truth)} known defect locations and {len(detections['positive'])} YOLO outputs", flush=True)
    overlay = positive.copy()
    for row in truth:
        row.update(mapped(row["pixel"], "crack", 1., "medium", .5, row))
        colour = (0, 140, 0) if row["correct_element"] else (0, 0, 200)
        pixel = tuple(row["pixel"])
        cv2.drawMarker(overlay, pixel, colour, cv2.MARKER_CROSS, 21, 2)
        error = f"{row['error_cm']:.1f} cm" if row["error_cm"] is not None else "unmapped"
        cv2.putText(overlay, f"{row['id']} {error}", (pixel[0] + 12, pixel[1] + 7),
                    cv2.FONT_HERSHEY_SIMPLEX, .57, colour, 2)
    cv2.imwrite(str(args.out / "06-bim-mapping.png"), overlay)
    for row in detections["positive"]:
        expected = next((item for item in truth if item["id"] == row.get("matches")), None)
        row.update(mapped(centre(row["box"]), row["defect_class"], row["confidence"],
                          row["severity"], row["severity_score"], expected))
    cv2.imwrite(str(args.out / "08-detector-to-bim.png"), combined_overlay(positive, detections["positive"]))
    columns = ["id", "element_type", "element_name", "element_guid", "pixel", "world",
               "mapped_guid", "mapped_world", "correct_element", "error_cm"]
    with (args.out / "mapping.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(truth)

    pose = cal.pnp_result
    header = PureWindowsPath(model.header.file_name.name).name
    checksum = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    evidence = dict(
        ifc_header=header, ifc_sha256=checksum(args.ifc), ifc_mesh_count=len(meshes),
        weights_sha256=checksum(weights), resolution=[WIDTH, HEIGHT], horizontal_fov_deg=FOV,
        virtual_camera_xyz=position.tolist(), virtual_camera_rotation=rotation.tolist(),
        marker=registry, decoded_marker_id=cal.detected_marker_id,
        calibration_passed=cal.success, calibration_error=cal.error_message,
        calibration_candidate_count=len(candidates), missing_marker_rejected=not no_marker.success,
        missing_marker_result=no_marker.error_message,
        recovered_camera_xyz=pose.camera_position_world.tolist() if pose and cal.success else None,
        recovered_camera_rotation=pose.rotation_matrix.tolist() if pose and cal.success else None,
        reprojection_error_px=pose.reprojection_error if pose and cal.success else None,
        pose_error_cm=float(100 * np.linalg.norm(pose.camera_position_world - position)) if pose and cal.success else None,
        confidence_threshold=threshold, matching_iou_threshold=.5, inference_ms=inference_ms,
        detection_true_positives=len(truth) - len(unmatched),
        detection_false_positives=len(detections["positive"]) - (len(truth) - len(unmatched)),
        detection_misses=[truth[index]["id"] for index in sorted(unmatched)],
        detections=detections, mapping=truth,
    )
    (args.out / "results.json").write_text(json.dumps(evidence, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Completed. Calibration={cal.success}; mapped correct={sum(r['correct_element'] for r in truth)}/{len(truth)};"
          f" YOLO matched={evidence['detection_true_positives']}/{len(truth)}", flush=True)


if __name__ == "__main__":
    main()
