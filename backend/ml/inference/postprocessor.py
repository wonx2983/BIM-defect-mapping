"""Post-processing utilities for defect detection results.

Handles annotation rendering (drawing bounding boxes on images),
defect clustering, and result filtering.
"""

import io
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ml.inference.detector import DetectionResult, InferenceResult

logger = logging.getLogger(__name__)

# Colors for each severity level (RGB)
SEVERITY_COLORS = {
    "low": (34, 197, 94),        # Green
    "medium": (234, 179, 8),     # Yellow
    "high": (249, 115, 22),      # Orange
    "critical": (239, 68, 68),   # Red
}

# Colors for each defect class (RGB)
CLASS_COLORS = {
    "crack": (239, 68, 68),
    "spalling": (249, 115, 22),
    "exposed_rebar": (220, 38, 38),
    "corrosion": (180, 83, 9),
    "water_seepage": (59, 130, 246),
    "honeycombing": (168, 85, 247),
}


def annotate_image(
    image: Image.Image,
    result: InferenceResult,
    color_by: str = "severity",
    line_width: int = 3,
    font_size: int = 14,
    show_confidence: bool = True,
    show_severity: bool = True,
) -> Image.Image:
    """Draw bounding boxes and labels on a copy of the image.

    Args:
        image: Original PIL Image.
        result: InferenceResult from the detector.
        color_by: "severity" or "class" — determines box color.
        line_width: Bounding box line width.
        font_size: Label font size.
        show_confidence: Show confidence % in the label.
        show_severity: Show severity badge in the label.

    Returns:
        Annotated copy of the image.
    """
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)

    # Try loading a monospace font, fall back to default
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()

    for detection in result.detections:
        bp = detection.bbox_pixels
        x1, y1, x2, y2 = bp["x1"], bp["y1"], bp["x2"], bp["y2"]

        # Choose color
        if color_by == "severity":
            color = SEVERITY_COLORS.get(detection.severity, (255, 255, 255))
        else:
            color = CLASS_COLORS.get(detection.defect_class, (255, 255, 255))

        # Draw bounding box
        draw.rectangle([x1, y1, x2, y2], outline=color, width=line_width)

        # Build label text
        parts = [detection.defect_class.replace("_", " ").title()]
        if show_confidence:
            parts.append(f"{detection.confidence * 100:.0f}%")
        if show_severity:
            parts.append(detection.severity.upper())
        label = " | ".join(parts)

        # Draw label background
        text_bbox = draw.textbbox((x1, y1), label, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        padding = 4
        label_y = max(y1 - text_h - padding * 2, 0)
        draw.rectangle(
            [x1, label_y, x1 + text_w + padding * 2, label_y + text_h + padding * 2],
            fill=color,
        )
        draw.text(
            (x1 + padding, label_y + padding),
            label,
            fill=(255, 255, 255),
            font=font,
        )

    return annotated


def image_to_bytes(image: Image.Image, format: str = "JPEG", quality: int = 90) -> bytes:
    """Convert a PIL Image to bytes."""
    buffer = io.BytesIO()
    image.save(buffer, format=format, quality=quality)
    return buffer.getvalue()


def filter_detections(
    result: InferenceResult,
    min_confidence: float = 0.0,
    classes: list[str] | None = None,
    severities: list[str] | None = None,
) -> InferenceResult:
    """Filter detections by confidence, class, or severity.

    Returns a new InferenceResult with only matching detections.
    """
    filtered = []
    for det in result.detections:
        if det.confidence < min_confidence:
            continue
        if classes and det.defect_class not in classes:
            continue
        if severities and det.severity not in severities:
            continue
        filtered.append(det)

    return InferenceResult(
        detections=filtered,
        image_width=result.image_width,
        image_height=result.image_height,
        inference_time_ms=result.inference_time_ms,
        model_name=result.model_name,
    )


def cluster_nearby_defects(
    detections: list[DetectionResult],
    distance_threshold: float = 0.1,
) -> list[list[DetectionResult]]:
    """Group nearby defects into clusters based on spatial proximity.

    Uses normalized bbox centers. Defects within distance_threshold
    of each other are grouped together. Useful for density analysis.
    """
    if not detections:
        return []

    # Calculate centers
    centers = []
    for d in detections:
        cx = d.bbox["x"] + d.bbox["w"] / 2
        cy = d.bbox["y"] + d.bbox["h"] / 2
        centers.append((cx, cy))

    # Simple greedy clustering
    assigned = [False] * len(detections)
    clusters: list[list[DetectionResult]] = []

    for i in range(len(detections)):
        if assigned[i]:
            continue
        cluster = [detections[i]]
        assigned[i] = True

        for j in range(i + 1, len(detections)):
            if assigned[j]:
                continue
            dist = ((centers[i][0] - centers[j][0]) ** 2 + (centers[i][1] - centers[j][1]) ** 2) ** 0.5
            if dist <= distance_threshold:
                cluster.append(detections[j])
                assigned[j] = True

        clusters.append(cluster)

    return clusters
