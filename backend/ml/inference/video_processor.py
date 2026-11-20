"""Video processing engine for defect detection.

Supports three modes:
1. Uploaded video files — process frame-by-frame, return aggregated results + annotated video
2. RTSP/CCTV streams — connect to IP camera, run inference on sampled frames
3. Individual frames — for webcam mode (frontend sends frames as images)
"""

import logging
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

import cv2
import numpy as np
from PIL import Image

from ml.inference.detector import DefectDetector, InferenceResult, DetectionResult

logger = logging.getLogger(__name__)


@dataclass
class FrameDetection:
    """Detection results for a single video frame."""
    frame_index: int
    timestamp_ms: float
    detections: list[DetectionResult]
    inference_time_ms: float


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

    def to_dict(self) -> dict:
        return {
            "counting_mode": "observations",
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
                    "snapshot_url": getattr(fd, 'snapshot_url', None),
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


def _iou(box1: dict, box2: dict) -> float:
    """Compute IoU between two bbox_pixels dicts."""
    x1 = max(box1["x1"], box2["x1"])
    y1 = max(box1["y1"], box2["y1"])
    x2 = min(box1["x2"], box2["x2"])
    y2 = min(box1["y2"], box2["y2"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1["x2"] - box1["x1"]) * (box1["y2"] - box1["y1"])
    area2 = (box2["x2"] - box2["x1"]) * (box2["y2"] - box2["y1"])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0


def _deduplicate_detections(all_frame_detections: list[FrameDetection], iou_threshold: float = 0.5) -> int:
    """Count unique defects across frames by merging overlapping boxes of the same class."""
    seen: list[tuple[str, dict]] = []  # (class, bbox_pixels) of unique defects

    for fd in all_frame_detections:
        for det in fd.detections:
            is_duplicate = False
            for seen_class, seen_box in seen:
                if det.defect_class == seen_class and _iou(det.bbox_pixels, seen_box) > iou_threshold:
                    is_duplicate = True
                    break
            if not is_duplicate:
                seen.append((det.defect_class, det.bbox_pixels))

    return len(seen)


def process_video_file(video_path, detector, frame_skip=10, output_dir=None, generate_annotated=True):
    from app.core.exceptions import ValidationError
    from app.services.uploads import upload_url
    if not 1 <= frame_skip <= 300:
        raise ValidationError("frame_skip must be between 1 and 300")
    cap = cv2.VideoCapture(video_path)
    writer = None
    result = VideoProcessingResult()
    started = time.monotonic()
    try:
        if not cap.isOpened():
            raise ValidationError("Video cannot be decoded")
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not np.isfinite(fps) or fps <= 0:
            raise ValidationError("Invalid video frame rate")
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
        # Screen coordinates do not establish physical identity for moving cameras.
        result.unique_defects = result.total_detections
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
