"""Video processing engine for defect detection.

Supports three modes:
1. Uploaded video files — process frame-by-frame, return aggregated results + annotated video
2. RTSP/CCTV streams — connect to IP camera, run inference on sampled frames
3. Individual frames — for webcam mode (frontend sends frames as images)
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ml.inference.detector import DetectionResult
from ml.inference.video_tracks import TRACK_MAX_GAP_MS, FrameDetection, VideoTrack, associate_fixed_camera

logger = logging.getLogger(__name__)


@dataclass
class VideoProcessingResult:
    """Aggregated results from processing an entire video."""
    total_frames: int = 0
    processed_frames: int = 0
    total_detections: int = 0
    unique_defects: int = 0
    duration_seconds: float = 0.0
    fps: float = 0.0
    processing_time_seconds: float = 0.0
    frame_detections: list[FrameDetection] = field(default_factory=list)
    severity_summary: dict = field(default_factory=lambda: {"low": 0, "medium": 0, "high": 0, "critical": 0})
    class_summary: dict = field(default_factory=dict)
    annotated_video_path: str | None = None
    tracks: list[VideoTrack] | None = None
    minimum_sightings: int = 1

    def finish(self, fixed_camera: bool) -> None:
        if fixed_camera:
            self.tracks = associate_fixed_camera(self.frame_detections)
        else:
            self.tracks = None
        self.unique_defects = len(self.review_tracks) if self.tracks is not None else self.total_detections

    @property
    def review_tracks(self) -> list[VideoTrack]:
        return [track for track in self.tracks or [] if track.sightings >= self.minimum_sightings]

    def to_dict(self) -> dict:
        return {
            "counting_mode": "fixed_camera_tracks" if self.tracks is not None else "observations",
            "tracks": [
                {**track.summary(), "eligible_for_review": track.sightings >= self.minimum_sightings}
                for track in self.tracks or []
            ],
            "minimum_sightings": self.minimum_sightings,
            "unconfirmed_groups": len(self.tracks) - self.unique_defects if self.tracks is not None else 0,
            "total_frames": self.total_frames,
            "processed_frames": self.processed_frames,
            "total_detections": self.total_detections,
            "unique_defects": self.unique_defects,
            "duration_seconds": round(self.duration_seconds, 2),
            "fps": round(self.fps, 2),
            "processing_time_seconds": round(self.processing_time_seconds, 2),
            "severity_summary": self.severity_summary,
            "class_summary": self.class_summary,

            "frame_detections": [
                {
                    "frame_index": fd.frame_index,
                    "timestamp_ms": round(fd.timestamp_ms, 1),
                    "detection_count": len(fd.detections),
                    "snapshot_url": fd.snapshot_url,
                    "detections": [
                        {
                            "defect_class": d.defect_class,
                            "confidence": round(d.confidence, 4),
                            "severity": d.severity,
                            "severity_score": round(d.severity_score, 4),
                            "bbox_pixels": d.bbox_pixels,
                        }
                        for d in fd.detections
                    ],
                }
                for fd in self.frame_detections
                if len(fd.detections) > 0  # Only include frames with detections
            ],
        }


def _draw_boxes_on_frame(frame: np.ndarray, detections: list[DetectionResult]) -> np.ndarray:
    """Draw bounding boxes and labels on a video frame."""
    SEVERITY_COLORS = {
        "low": (0, 180, 100),       # Green (BGR)
        "medium": (0, 180, 255),    # Orange
        "high": (0, 100, 255),      # Red-orange
        "critical": (0, 0, 255),    # Red
    }

    annotated = frame.copy()
    for det in detections:
        color = SEVERITY_COLORS.get(det.severity, (255, 255, 255))
        bp = det.bbox_pixels
        x1, y1, x2, y2 = int(bp["x1"]), int(bp["y1"]), int(bp["x2"]), int(bp["y2"])

        # Draw box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        # Draw label background
        label = f"{det.defect_class} {det.confidence:.0%} [{det.severity}]"
        font_scale = 0.5
        thickness = 1
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        cv2.rectangle(annotated, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness)

    return annotated


def process_video_file(video_path, detector, frame_skip=10, output_dir=None,
                       generate_annotated=True, fixed_camera=False, minimum_sightings=1):
    from app.core.exceptions import ValidationError
    from app.services.uploads import upload_url
    if not 1 <= frame_skip <= 300:
        raise ValidationError("frame_skip must be between 1 and 300")
    if minimum_sightings < 1 or (minimum_sightings > 1 and not fixed_camera):
        raise ValidationError("Repeat confirmation requires a fixed camera")
    cap = cv2.VideoCapture(video_path)
    writer = None
    result = VideoProcessingResult(minimum_sightings=minimum_sightings)
    started = time.monotonic()
    try:
        if not cap.isOpened():
            raise ValidationError("Video cannot be decoded")
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not np.isfinite(fps) or fps <= 0:
            raise ValidationError("Invalid video frame rate")
        if minimum_sightings > 1 and frame_skip / fps * 1000 > TRACK_MAX_GAP_MS:
            raise ValidationError("Choose a faster sampling rate to confirm sightings within two seconds")
        width, height = int(cap.get(3)), int(cap.get(4))
        if width <= 0 or height <= 0 or width * height > 16_777_216:
            raise ValidationError("Unsupported video resolution")
        result.fps = fps
        if output_dir and generate_annotated:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            # Downloadable MP4; browser preview support depends on installed codecs.
            result.annotated_video_path = str(Path(output_dir) / f"annotated_{uuid.uuid4().hex}.mp4")
            writer = cv2.VideoWriter(result.annotated_video_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
            if not writer.isOpened():
                raise ValidationError("Video encoder unavailable")
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if time.monotonic() - started > 600 or result.total_frames >= 108000:
                raise ValidationError("Video processing limit exceeded; split the video into shorter clips")
            index = result.total_frames
            if index % frame_skip == 0:
                if result.processed_frames >= 1000:
                    raise ValidationError("At most 1000 sampled frames per upload; increase frame_skip")
                inference = detector.predict(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                fd = FrameDetection(index, index / fps * 1000, inference.detections, inference.inference_time_ms)
                annotated = _draw_boxes_on_frame(frame, inference.detections)
                if inference.detections and output_dir:
                    path = Path(output_dir) / f"frame_{index}_{uuid.uuid4().hex}.jpg"
                    if not cv2.imwrite(str(path), annotated):
                        raise RuntimeError("Could not save evidence snapshot")
                    fd.snapshot_url = upload_url(path)
                result.frame_detections.append(fd)
                result.processed_frames += 1
                result.total_detections += len(inference.detections)
                for det in inference.detections:
                    result.severity_summary[det.severity] += 1
                    result.class_summary[det.defect_class] = result.class_summary.get(det.defect_class, 0) + 1
                if writer:
                    writer.write(annotated)
            elif writer:
                writer.write(frame)
            result.total_frames += 1
        if result.total_frames == 0:
            raise ValidationError("Video contains no readable frames")
        result.finish(fixed_camera)
        result.duration_seconds = result.total_frames / fps
        result.processing_time_seconds = time.monotonic() - started
        return result
    finally:
        cap.release()
        if writer:
            writer.release()


def process_rtsp_frames(rtsp_url, detector, frame_skip=10, max_frames=100):
    from app.services.streams import open_stream
    from app.core.config import get_settings
    from app.core.exceptions import AppException, ValidationError
    if not 1 <= frame_skip <= 300 or not 1 <= max_frames <= 300:
        raise ValidationError("Invalid sampling limits")
    cap = open_stream(rtsp_url)
    started = time.monotonic()
    processed = index = 0
    try:
        while processed < max_frames:
            if time.monotonic() - started > get_settings().STREAM_MAX_SECONDS:
                raise AppException("Camera analysis exceeded its time limit", "STREAM_TIMEOUT", 504)
            ret, frame = cap.read()
            if not ret or frame is None:
                raise AppException("Camera stream disconnected", "STREAM_DISCONNECTED", 502)
            if frame.shape[0] * frame.shape[1] > 16_777_216:
                raise ValidationError("Camera resolution exceeds limit")
            if index % frame_skip == 0:
                result = detector.predict(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                processed += 1
                yield index, result, _draw_boxes_on_frame(frame, result.detections)
            index += 1
    finally:
        cap.release()
