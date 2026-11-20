"""Associate repeated detections in one stationary-camera clip."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

TRACK_MAX_GAP_MS = 2000

if TYPE_CHECKING:
    from ml.inference.detector import DetectionResult


@dataclass
class FrameDetection:
    frame_index: int
    timestamp_ms: float
    detections: list[DetectionResult]
    inference_time_ms: float
    snapshot_url: str | None = None


@dataclass
class VideoTrack:
    first_seen_ms: float
    last_seen_ms: float
    last_box: dict
    best_detection: DetectionResult
    best_frame: FrameDetection
    sightings: int = 1
    second_seen_ms: float | None = None

    def add(self, frame: FrameDetection, detection: DetectionResult) -> None:
        self.last_seen_ms = frame.timestamp_ms
        self.last_box = detection.bbox_pixels
        self.sightings += 1
        if self.sightings == 2:
            self.second_seen_ms = frame.timestamp_ms
        if detection.confidence > self.best_detection.confidence:
            self.best_detection = detection
            self.best_frame = frame

    def summary(self) -> dict:
        return {
            "defect_class": self.best_detection.defect_class,
            "confidence": round(self.best_detection.confidence, 4),
            "first_seen_ms": round(self.first_seen_ms, 1),
            "last_seen_ms": round(self.last_seen_ms, 1),
            "sightings": self.sightings,
            "second_seen_ms": round(self.second_seen_ms, 1) if self.second_seen_ms is not None else None,
            "evidence_frame_index": self.best_frame.frame_index,
            "snapshot_url": self.best_frame.snapshot_url,
        }


def box_iou(first: dict, second: dict) -> float:
    width = max(0, min(first["x2"], second["x2"]) - max(first["x1"], second["x1"]))
    height = max(0, min(first["y2"], second["y2"]) - max(first["y1"], second["y1"]))
    intersection = width * height
    union = sum((box["x2"] - box["x1"]) * (box["y2"] - box["y1"]) for box in (first, second)) - intersection
    return intersection / union if union > 0 else 0.0


def associate_fixed_camera(frames: list[FrameDetection], max_gap_ms: float = TRACK_MAX_GAP_MS,
                           min_iou: float = 0.5) -> list[VideoTrack]:
    """Match at most one same-class sighting per track and sampled frame."""
    tracks: list[VideoTrack] = []
    active: list[int] = []
    for frame in frames:
        active = [index for index in active
                  if frame.timestamp_ms - tracks[index].last_seen_ms <= max_gap_ms]
        matches = []
        for track_index in active:
            track = tracks[track_index]
            for detection_index, detection in enumerate(frame.detections):
                if detection.defect_class == track.best_detection.defect_class:
                    overlap = box_iou(track.last_box, detection.bbox_pixels)
                    if overlap >= min_iou:
                        matches.append((overlap, track_index, detection_index))

        used_tracks = set()
        used_detections = set()
        for _, track_index, detection_index in sorted(matches, key=lambda match: -match[0]):
            if track_index in used_tracks or detection_index in used_detections:
                continue
            tracks[track_index].add(frame, frame.detections[detection_index])
            used_tracks.add(track_index)
            used_detections.add(detection_index)

        for index, detection in enumerate(frame.detections):
            if index not in used_detections:
                active.append(len(tracks))
                tracks.append(VideoTrack(frame.timestamp_ms, frame.timestamp_ms,
                                         detection.bbox_pixels, detection, frame))
    return tracks
