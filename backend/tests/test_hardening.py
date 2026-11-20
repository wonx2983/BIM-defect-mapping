import io
import uuid
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from sqlalchemy import select
from pydantic import ValidationError
from app.core.exceptions import AppException
from app.models import Defect
from app.models.user import UserRole
from app.schemas.bim import CameraCreate
from app.schemas.calibration import MarkerCreate
from ml.inference.detector import DetectionResult, InferenceResult, DefectDetector
from ml.inference.video_processor import FrameDetection
from ml.calibration.camera_calibrator import calibrate_camera_from_frame
from ml.calibration.pose_solver import CameraIntrinsics
from ml.calibration.raycaster import pixel_to_ray
from app.services.streams import validate_stream_url
import test_phase2_synthetic_e2e as scene


def synthetic_scene():
    R, t, intrinsics = scene.build_camera_matrices(scene.GT_CAMERA_POS, scene.GT_LOOK_AT,
        scene.GT_UP, scene.FOV_H_DEG, scene.IMAGE_W, scene.IMAGE_H)
    frame = scene.generate_synthetic_frame(R, t, intrinsics.matrix, scene.MARKERS, scene.IMAGE_W, scene.IMAGE_H)
    registry = []
    for m in scene.MARKERS:
        entry = {"id": str(uuid.uuid4()), "marker_dict_id": m["id"], "physical_size_m": m["size_m"]}
        entry.update(zip(("world_x", "world_y", "world_z"), m["world_pos"]))
        entry.update(zip(("normal_x", "normal_y", "normal_z"), m["normal"]))
        registry.append(entry)
    return R, intrinsics, frame, registry


def detection(confidence=0.7, severity="medium"):
    return DetectionResult("crack", confidence, severity, confidence,
        {"x": .46875, "y": .46296, "w": .0625, "h": .07407},
        {"x1": 900, "y1": 500, "x2": 1020, "y2": 580},
        {"width_px": 120, "height_px": 80, "area_px": 9600})


def test_actual_calibrator_uses_all_markers_and_rejects_insufficient_evidence():
    _, intrinsics, frame, registry = synthetic_scene()
    result = calibrate_camera_from_frame(frame, registry, intrinsics=intrinsics)
    assert result.success
    assert result.pnp_result.reprojection_error < 1
    assert np.linalg.norm(result.pnp_result.camera_position_world - scene.GT_CAMERA_POS) < .2
    single = calibrate_camera_from_frame(frame, registry[:1], intrinsics=intrinsics)
    assert single.success
    assert np.linalg.norm(single.pnp_result.camera_position_world - scene.GT_CAMERA_POS) < 1.0
    assert not calibrate_camera_from_frame(frame, [], intrinsics=intrinsics).success


def test_calibration_rejects_high_reprojection(monkeypatch):
    _, intrinsics, frame, registry = synthetic_scene()
    monkeypatch.setattr("ml.calibration.camera_calibrator.solve_pnp", lambda *a, **k:
        SimpleNamespace(success=True, reprojection_error=21.0))
    assert not calibrate_camera_from_frame(frame, registry, intrinsics=intrinsics).success


def test_distorted_pixel_is_undistorted():
    import cv2
    K = np.array([[800., 0, 640], [0, 800, 360], [0, 0, 1]])
    distortion = np.array([.2, -.05, .01, .005, 0.])
    point = np.array([[1., .5, 3.]])
    pixel = cv2.projectPoints(point, np.zeros(3), np.zeros(3), K, distortion)[0][0, 0]
    ray = pixel_to_ray(*pixel, 800, 800, 640, 360, np.eye(3), np.zeros(3), distortion)
    assert np.allclose(ray.direction, point[0] / np.linalg.norm(point[0]), atol=1e-5)


def test_missing_weights_fail_closed(tmp_path):
    with pytest.raises(RuntimeError, match="unavailable"):
        DefectDetector(tmp_path / "missing.pt")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://camera.example", "rtsp://localhost/x", "rtsp://169.254.169.254/x", "rtsp://other.example/x"])
def test_stream_url_policy(url):
    with pytest.raises(AppException):
        validate_stream_url(url)


def test_invalid_camera_sampling_and_marker_geometry():
    with pytest.raises(ValidationError):
        CameraCreate(name="x", rtsp_url="rtsp://camera.example/live", project_id=uuid.uuid4(), frame_skip=0)
    with pytest.raises(ValidationError):
        MarkerCreate(project_id=uuid.uuid4(), marker_dict_id=0, world_x=0, world_y=0,
                     world_z=0, normal_x=0, normal_y=0, normal_z=0, physical_size_m=.2)


async def test_cross_organization_resources_are_inaccessible(context):
    c = context
    camera_id, model_id = c.cameras[1].id, c.models[1].id
    paths = [f"/api/v1/cameras/{c.cameras[1].id}",
             f"/api/v1/bim/model/{c.models[1].id}",
             f"/api/v1/bim/{c.projects[1].id}/models",
             f"/api/v1/bim/{c.projects[1].id}/defects-mapped",
             f"/api/v1/calibration/{c.cameras[1].id}/status"]
    for path in paths:
        response = await c.client.get(path)
        assert response.status_code == 404, (path, response.text)
    assert (await c.client.put(f"/api/v1/cameras/{camera_id}", json={"name": "bad"})).status_code == 404
    assert (await c.client.delete(f"/api/v1/bim/model/{model_id}")).status_code == 404


async def test_cross_project_upload_rejected_before_inference(context, monkeypatch):
    c = context
    async def forbidden(*args):
        raise AssertionError("Inference must not run")
    monkeypatch.setattr("app.api.v1.detection.run_inference_and_annotate", forbidden)
    response = await c.client.post("/api/v1/detect/image", data={"project_id": str(c.projects[1].id)},
                                   files={"file": ("image.jpg", b"not-an-image", "image/jpeg")})
    assert response.status_code == 404


async def test_preview_does_not_write_files(context, monkeypatch):
    async def inference(data):
        return InferenceResult([detection()], 1920, 1080, 1., "test"), b"jpeg-preview"
    monkeypatch.setattr("app.api.v1.detection.run_inference_and_annotate", inference)
    response = await context.client.post("/api/v1/detect/image", data={
        "project_id": str(context.projects[0].id), "auto_save": "false"},
        files={"file": ("image.jpg", b"bytes", "image/jpeg")})
    assert response.status_code == 200, response.text
    assert response.json()["annotated_image_url"].startswith("data:image/jpeg;base64,")
    assert not list(context.tmp.rglob("*.jpg"))
    assert not (await context.db.scalars(select(Defect))).all()


async def test_private_media_rejects_foreign_and_anonymous_access(context):
    from app.services.uploads import project_directory, upload_url
    path = project_directory(context.projects[1].id, "inspections") / "private.jpg"
    path.write_bytes(b"secret image")
    assert (await context.client.get(upload_url(path))).status_code == 404
    response = await context.client.get(upload_url(path), headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


async def test_camera_response_and_calibration_invalidation(context):
    cam = context.cameras[0]
    cam.calibration_status = "calibrated"
    cam.candidate_element_guids = ["wall"]
    cam.pose_rotation = {"matrix": np.eye(3).flatten().tolist()}
    await context.db.commit()
    response = await context.client.get(f"/api/v1/cameras/{cam.id}")
    assert response.status_code == 200, response.text
    assert response.json()["candidate_element_guids"] == ["wall"]
    response = await context.client.put(f"/api/v1/cameras/{cam.id}", json={"rtsp_url": "rtsp://camera.example/new"})
    assert response.status_code == 200, response.text
    assert response.json()["calibration_status"] == "uncalibrated"


async def test_auto_mapping_api_centroid_and_duplicate_persistence(context, monkeypatch):
    c = context
    cam = c.cameras[0]
    rotation, intrinsics, _, _ = synthetic_scene()
    cam.calibration_status = "calibrated"
    cam.intrinsics = intrinsics.to_dict()
    cam.pose_rotation = {"matrix": rotation.flatten().tolist()}
    cam.pose_translation = dict(zip(("x", "y", "z"), scene.GT_CAMERA_POS.tolist()))
    cam.image_width, cam.image_height = 1920, 1080
    cam.candidate_element_guids = ["wall-north-001"]
    await c.db.commit()
    frame = FrameDetection(0, 0, [detection(.7), detection(.95, "high")], 1.)
    frame.snapshot_url = "/uploads/test-evidence.jpg"
    monkeypatch.setattr("app.api.v1.calibration.get_detector", lambda: object())
    monkeypatch.setattr("app.services.camera_capture.capture_observations", lambda *a: [frame])
    monkeypatch.setattr("app.api.v1.calibration._get_ifc_path", lambda *a: Path("synthetic.ifc"))
    monkeypatch.setattr("ml.calibration.ifc_geometry.extract_meshes_from_ifc", lambda *a: scene.build_box_room_meshes())
    response = await c.client.post(f"/api/v1/calibration/{cam.id}/auto-detect?max_frames=2")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mapped_count"] == 1 and result["deduplicated_count"] == 1
    assert result["results"][0]["defect_id"] == result["results"][1]["defect_id"]
    defects = (await c.db.scalars(select(Defect))).all()
    assert len(defects) == 1
    assert defects[0].confidence == .95 and defects[0].severity.value == "high"
    assert defects[0].world_position == pytest.approx({"x": 5., "y": 10., "z": 1.5})


async def test_manually_triggered_ray_miss_preserves_unmapped_evidence(context, monkeypatch):
    from ml.calibration import ifc_geometry

    camera = context.cameras[0]
    rotation, intrinsics, _, _ = synthetic_scene()
    camera.calibration_status = "calibrated"
    camera.intrinsics = intrinsics.to_dict()
    camera.pose_rotation = {"matrix": rotation.flatten().tolist()}
    camera.pose_translation = dict(zip(("x", "y", "z"), scene.GT_CAMERA_POS.tolist()))
    camera.image_width, camera.image_height = 1920, 1080
    camera.candidate_element_guids = ["wall-north-001"]
    await context.db.commit()
    frame = FrameDetection(0, 0, [detection()], 1, "/uploads/miss.jpg")
    monkeypatch.setattr("app.api.v1.calibration.get_detector", lambda: object())
    monkeypatch.setattr("app.services.camera_capture.capture_observations", lambda *a: [frame])
    monkeypatch.setattr("app.api.v1.calibration._get_ifc_path", lambda *a: Path("miss.ifc"))
    monkeypatch.setattr(ifc_geometry, "extract_meshes_from_ifc", lambda *a: {
        guid: (vertices + 100, faces) for guid, (vertices, faces) in scene.build_box_room_meshes().items()
    })
    url = f"/api/v1/calibration/{camera.id}/auto-detect"
    scheduled = await context.client.post(url, params={"persist_unmapped": False})
    assert scheduled.status_code == 200, scheduled.text
    assert scheduled.json()["results"][0]["defect_id"] is None
    response = await context.client.post(url)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mapped_count"] == 0 and result["unmapped_count"] == 1
    item = result["results"][0]
    assert item["mapping_error"]
    defect, = (await context.db.scalars(select(Defect))).all()
    assert str(defect.id) == item["defect_id"]
    assert defect.bim_element_guid is None and defect.world_position is None
    assert defect.source_image_url == "/uploads/miss.jpg"
    listing = await context.client.get(f"/api/v1/bim/{camera.project_id}/defects-mapped",
                                       params={"model_id": str(camera.bim_model_id)})
    assert listing.status_code == 200, listing.text
    assert [row["id"] for row in listing.json()["unmapped"]] == [str(defect.id)]


async def test_rtsp_failure_is_not_completed(context, monkeypatch):
    def fail(*a, **k):
        raise AppException("Camera offline", "CAMERA_UNAVAILABLE", 502)
    monkeypatch.setattr("app.api.v1.video.get_detector", lambda: object())
    monkeypatch.setattr("ml.inference.video_processor.process_rtsp_frames", fail)
    response = await context.client.post("/api/v1/video/stream/analyze", data={
        "project_id": str(context.projects[0].id), "rtsp_url": "rtsp://camera.example/live"})
    assert response.status_code == 502, response.text


async def test_viewer_cannot_write(context):
    context.users[0].role = UserRole.VIEWER
    await context.db.commit()
    response = await context.client.post("/api/v1/projects/", json={"name": "Forbidden"})
    assert response.status_code == 403


async def test_saved_inspection_has_audit_and_csv(context, monkeypatch):
    from app.models.audit import AuditEvent
    from app.models.inspection import Inspection
    async def inference(data):
        return InferenceResult([detection()], 1920, 1080, 1., "test"), b"jpeg-preview"
    monkeypatch.setattr("app.api.v1.detection.run_inference_and_annotate", inference)
    project_id = str(context.projects[0].id)
    response = await context.client.post("/api/v1/detect/image", data={
        "project_id": project_id, "auto_save": "true"},
        files={"file": ("image.jpg", b"bytes", "image/jpeg")})
    assert response.status_code == 200, response.text
    defect = (await context.db.scalars(select(Defect))).one()
    assert defect.inspection_id is not None
    assert (await context.db.scalars(select(Inspection))).one().id == defect.inspection_id
    assert (await context.db.scalars(select(AuditEvent))).one().action == "created"
    response = await context.client.put(f"/api/v1/defects/{defect.id}", json={"notes": "=HYPERLINK(unsafe)"})
    assert response.status_code == 200, response.text
    response = await context.client.get(f"/api/v1/reports/{project_id}/defects.csv")
    assert response.status_code == 200
    assert "'=HYPERLINK(unsafe)" in response.text
    events = (await context.client.get(f"/api/v1/reports/{project_id}/audit")).json()
    assert {event["action"] for event in events} == {"created", "updated"}


async def test_private_media_cookie_is_read_only(context):
    from app.services.uploads import project_directory, upload_url
    from app.core.security import create_access_token
    path = project_directory(context.projects[0].id, "inspections") / "private.jpg"
    path.write_bytes(b"private image")
    context.client.headers.pop("Authorization")
    assert (await context.client.get(upload_url(path))).status_code == 401
    context.client.cookies.set("defectsync_media", create_access_token({"sub": str(context.users[0].id)}))
    assert (await context.client.get(upload_url(path))).status_code == 200
    assert (await context.client.post("/api/v1/projects/", json={"name": "Cookie mutation"})).status_code == 401


async def test_camera_null_update_is_rejected(context):
    response = await context.client.put(f"/api/v1/cameras/{context.cameras[0].id}", json={"frame_skip": None})
    assert response.status_code == 422


async def test_marker_update_rejects_zero_normal(context):
    c = context
    response = await c.client.post("/api/v1/markers/", json={"project_id": str(c.projects[0].id),
        "bim_model_id": str(c.models[0].id), "marker_dict_id": 0, "physical_size_m": .2,
        "world_x": 1, "world_y": 2, "world_z": 3})
    assert response.status_code == 201, response.text
    response = await c.client.put(f"/api/v1/markers/{response.json()['id']}", json={"normal_z": 0})
    assert response.status_code == 422, response.text


async def test_bounded_upload_removes_partial_file(context):
    from starlette.datastructures import UploadFile
    from app.services.uploads import stream_upload
    with pytest.raises(AppException):
        await stream_upload(UploadFile(filename="big.mp4", file=io.BytesIO(b"x" * 32)),
                            context.projects[0].id, "videos", 10, {".mp4"})
    assert not list(context.tmp.rglob("*.mp4"))
