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
            "total_frames": self.total_frames,
            "processed_frames": self.processed_frames,
            "total_detections": self.total_detections,
            "unique_defects": self.unique_defects,
            "duration_seconds": round(self.duration_seconds, 2),
            "fps": round(self.fps, 2),
            "processing_time_seconds": round(self.processing_time_seconds, 2),
            "severity_summary": self.severity_summary,
            "class_summary": self.class_summary,
            "annotated_video_path": self.annotated_video_path,
            "frame_detections": [
                {
                    "frame_index": fd.frame_index,
                    "timestamp_ms": round(fd.timestamp_ms, 1),
                    "detection_count": len(fd.detections),
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


def process_video_file(
    video_path: str,
    detector: DefectDetector,
    frame_skip: int = 10,
    output_dir: str | None = None,
    generate_annotated: bool = True,
) -> VideoProcessingResult:
    """Process an uploaded video file frame-by-frame with the YOLO detector.

    Args:
        video_path: Path to the input video file.
        detector: Loaded DefectDetector instance.
        frame_skip: Process every Nth frame (default: every 10th frame).
        output_dir: Directory to save annotated output video.
        generate_annotated: Whether to generate an annotated output video.

    Returns:
        VideoProcessingResult with aggregated detections.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")

    # Video properties
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps if fps > 0 else 0

    logger.info(f"Processing video: {total_frames} frames, {fps:.1f} fps, {width}x{height}, {duration:.1f}s")

    # Output video writer
    writer = None
    annotated_path = None
    if generate_annotated and output_dir:
        annotated_path = str(Path(output_dir) / f"annotated_{uuid.uuid4().hex[:8]}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(annotated_path, fourcc, fps, (width, height))

    result = VideoProcessingResult(
        total_frames=total_frames,
        fps=fps,
        duration_seconds=duration,
    )

    start_time = time.time()
    frame_index = 0
    all_detections_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_index % frame_skip == 0:
            # Convert BGR → RGB for PIL
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)

            # Run inference
            t0 = time.time()
            inference_result = detector.predict(pil_image)
            inference_ms = (time.time() - t0) * 1000

            frame_det = FrameDetection(
                frame_index=frame_index,
                timestamp_ms=frame_index / fps * 1000 if fps > 0 else 0,
                detections=inference_result.detections,
                inference_time_ms=inference_ms,
            )
            result.frame_detections.append(frame_det)
            result.processed_frames += 1
            all_detections_count += len(inference_result.detections)

            # Update severity & class summaries
            for det in inference_result.detections:
                result.severity_summary[det.severity] = result.severity_summary.get(det.severity, 0) + 1
                result.class_summary[det.defect_class] = result.class_summary.get(det.defect_class, 0) + 1

            # Write annotated frame
            if writer and generate_annotated:
                annotated_frame = _draw_boxes_on_frame(frame, inference_result.detections)
                writer.write(annotated_frame)
            elif writer:
                writer.write(frame)
        else:
            # Write original frame for non-processed frames
            if writer:
                writer.write(frame)

        frame_index += 1

    cap.release()
    if writer:
        writer.release()

    result.total_detections = all_detections_count
    result.unique_defects = _deduplicate_detections(result.frame_detections)
    result.processing_time_seconds = time.time() - start_time
    result.annotated_video_path = annotated_path

    logger.info(
        f"Video processing complete: {result.processed_frames}/{result.total_frames} frames, "
        f"{result.unique_defects} unique defects, {result.processing_time_seconds:.1f}s"
    )

    return result


def process_rtsp_frames(
    rtsp_url: str,
    detector: DefectDetector,
    frame_skip: int = 10,
    max_frames: int = 300,
) -> Generator[tuple[int, InferenceResult, np.ndarray | None], None, None]:
    """Connect to an RTSP stream and yield inference results per sampled frame.

    This is a generator — the caller consumes frames as they arrive.

    Args:
        rtsp_url: RTSP URL of the IP camera (e.g., rtsp://user:pass@ip:554/stream)
        detector: Loaded DefectDetector instance.
        frame_skip: Process every Nth frame.
        max_frames: Maximum number of frames to process before stopping.

    Yields:
        (frame_index, InferenceResult, annotated_frame_bgr)
    """
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        raise ValueError(f"Cannot connect to RTSP stream: {rtsp_url}")

    logger.info(f"Connected to RTSP stream: {rtsp_url}")
    frame_index = 0
    processed = 0

    try:
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                logger.warning("RTSP stream ended or lost connection")
                break

            if frame_index % frame_skip == 0:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_frame)
                result = detector.predict(pil_image)
                annotated = _draw_boxes_on_frame(frame, result.detections)
                processed += 1
                yield frame_index, result, annotated

            frame_index += 1
    finally:
        cap.release()
        logger.info(f"RTSP stream closed after {processed} processed frames")
