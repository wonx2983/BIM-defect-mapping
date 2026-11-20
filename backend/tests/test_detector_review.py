from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api.v1 import video as video_api
from app.core.exceptions import ValidationError
from app.models.defect import Defect
from ml.evaluate_detector import score_image, summarize
from ml.inference.detector import DetectionResult
from ml.inference.video_processor import VideoProcessingResult, process_video_file
from ml.inference.video_tracks import FrameDetection, associate_fixed_camera


def prediction(x=0, confidence=0.8, defect_class="crack"):
    return {
        "defect_class": defect_class,
        "confidence": confidence,
        "bbox_pixels": {"x1": x, "y1": 0, "x2": x + 20, "y2": 20},
    }


def detection(x=0, confidence=0.8, defect_class="crack"):
    return DetectionResult(**prediction(x, confidence, defect_class),
                           severity="medium", severity_score=0.3, bbox={}, dimensions={})


def test_track_association_preserves_same_frame_detections_and_expires():
    frames = [
        FrameDetection(0, 0, [detection(), detection(8)], 1),
        FrameDetection(1, 500, [detection(9, 0.9), detection(1, 0.95)], 1),
        FrameDetection(2, 1000, [detection(defect_class="spalling")], 1),
        FrameDetection(3, 3000, [detection()], 1),
    ]
    tracks = associate_fixed_camera(frames)
    assert [track.sightings for track in tracks] == [2, 2, 1, 1]
    assert tracks[0].best_detection.confidence == 0.95
    assert tracks[1].best_detection.confidence == 0.9
    assert tracks[0].summary()["evidence_frame_index"] == 1
    assert tracks[0].last_seen_ms == 500


def test_scoring_counts_duplicates_wrong_classes_and_clean_alerts():
    labels = [prediction(), prediction(45)]
    positive = score_image([prediction(), prediction(confidence=0.7),
                            prediction(45, defect_class="spalling")], labels, 0.5)
    clean = score_image([prediction()], [], 0.5)
    summary = summarize([
        {"session": "A", "labels": labels, "inference_ms": 8, **positive},
        {"session": "B", "labels": [], "inference_ms": 12, **clean},
    ], ["crack", "spalling", "scaling"])
    assert summary["overall"] == {
        "tp": 1, "fp": 3, "fn": 1, "precision": 0.25, "recall": 0.5, "f1": 1 / 3,
    }
    assert summary["clean_images_with_alerts"] == 1
    assert summary["by_class"]["scaling"]["recall"] is None


def test_confirmation_rejects_sampling_beyond_association_window(monkeypatch):
    released = []
    capture = SimpleNamespace(isOpened=lambda: True, get=lambda _: 10,
                              release=lambda: released.append(True))
    monkeypatch.setattr("ml.inference.video_processor.cv2.VideoCapture", lambda _: capture)
    with pytest.raises(ValidationError, match="faster sampling"):
        process_video_file("sample.mp4", object(), frame_skip=30, fixed_camera=True, minimum_sightings=2)
    assert released == [True]


async def test_video_upload_saves_one_record_per_opt_in_track(context, monkeypatch):
    def process(*, fixed_camera, minimum_sightings, **kwargs):
        result = VideoProcessingResult(minimum_sightings=minimum_sightings, total_detections=3, frame_detections=[
            FrameDetection(0, 0, [detection(), detection(50)], 1, "/uploads/first.jpg"),
            FrameDetection(1, 500, [detection(1, 0.95)], 1, "/uploads/best.jpg"),
        ])
        result.finish(fixed_camera)
        return result

    monkeypatch.setattr(video_api, "process_video_file", process)
    monkeypatch.setattr(video_api, "get_detector", SimpleNamespace)
    for fixed_camera, confirm, expected in (("false", "false", 3), ("true", "false", 2), ("true", "true", 1)):
        response = await context.client.post("/api/v1/video/upload", files={
            "file": ("clip.mp4", b"mock clip", "video/mp4"),
        }, data={"project_id": str(context.projects[0].id), "fixed_camera": fixed_camera, "confirm_repeats": confirm})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["saved_defect_count"] == expected
        assert payload["unique_defects"] == expected
        assert payload["total_detections"] == 3
        if fixed_camera == "true":
            assert payload["tracks"][0]["snapshot_url"] == "/uploads/best.jpg"
        if confirm == "true":
            assert payload["unconfirmed_groups"] == 1
            assert payload["tracks"][0]["second_seen_ms"] == 500
            assert not payload["tracks"][1]["eligible_for_review"]
            assert payload["frame_detections"][0]["detection_count"] == 2
    records = (await context.db.execute(select(Defect))).scalars().all()
    assert len(records) == 6
    grouped = [item for item in records if item.notes.startswith("Fixed-camera") and item.confidence == 0.95]
    assert len(grouped) == 2
    assert all(item.source_image_url == "/uploads/best.jpg" for item in grouped)
