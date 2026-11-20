"""Offline audit probes. Run from the project root: python docs/reproduce_audit_findings.py.

Does not connect to the database, cameras, or external services. These probes
describe current behavior; they are not a replacement for regression tests.
"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

import numpy as np
from pydantic import TypeAdapter, ValidationError
from app.schemas.bim import CameraResponse
from ml.calibration.camera_calibrator import calibrate_camera_from_frame
import test_phase2_synthetic_e2e as scene


def main():
    # Execute the actual centroid assignments extracted from the API source.
    source = ROOT / "backend/app/api/v1/calibration.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    assignments = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id in ("cx", "cy") for t in n.targets)]
    scope = {"bbox": {"x1": 900, "y1": 500, "x2": 1020, "y2": 580}}
    exec(compile(ast.Module(body=assignments, type_ignores=[]), str(source), "exec"), scope)
    print("API centroid:", (scope["cx"], scope["cy"]), "expected:", (960, 540))

    annotation = CameraResponse.model_fields["candidate_element_guids"].annotation
    try:
        TypeAdapter(annotation).validate_python(["example-wall-guid"])
        print("Camera candidate-list response: accepted")
    except ValidationError:
        print("Camera candidate-list response: REJECTED (calibration stores a list)")

    rotation, translation, intrinsics = scene.build_camera_matrices(
        scene.GT_CAMERA_POS, scene.GT_LOOK_AT, scene.GT_UP,
        scene.FOV_H_DEG, scene.IMAGE_W, scene.IMAGE_H,
    )
    frame = scene.generate_synthetic_frame(
        rotation, translation, intrinsics.matrix, scene.MARKERS,
        scene.IMAGE_W, scene.IMAGE_H,
    )
    registry = []
    for marker in scene.MARKERS:
        record = {"id": str(marker["id"]), "marker_dict_id": marker["id"],
                  "physical_size_m": marker["size_m"]}
        record.update(zip(("world_x", "world_y", "world_z"), marker["world_pos"]))
        record.update(zip(("normal_x", "normal_y", "normal_z"), marker["normal"]))
        registry.append(record)
    result = calibrate_camera_from_frame(
        frame, registry, intrinsics=intrinsics, fov_horizontal_deg=scene.FOV_H_DEG,
    )
    output = {"production_calibrator_success": result.success,
              "error_message": result.error_message}
    if result.pnp_result is not None:
        output["reprojection_error_px"] = result.pnp_result.reprojection_error
        output["camera_position_error_m"] = float(np.linalg.norm(
            result.pnp_result.camera_position_world - scene.GT_CAMERA_POS))
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
