"""Unified defect detection pipeline.

Image → YOLOv11 Detection → Crop Defects → Severity Classification → Structured Results

This is the main inference entry point used by the API. It coordinates
the YOLO detector and the severity classifier into a single pipeline.
"""

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """Single detected defect with classification and severity."""

    defect_class: str
    confidence: float
    severity: str
    severity_score: float
    bbox: dict  # {x, y, w, h} — normalized coordinates
    bbox_pixels: dict  # {x1, y1, x2, y2} — pixel coordinates
    dimensions: dict  # {width_px, height_px, area_px}


@dataclass
class InferenceResult:
    """Full inference output for a single image."""

    detections: list[DetectionResult] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    inference_time_ms: float = 0.0
    model_name: str = ""

    @property
    def detection_count(self) -> int:
        return len(self.detections)

    @property
    def severity_summary(self) -> dict:
        summary = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for det in self.detections:
            summary[det.severity] += 1
        return summary

    def to_dict(self) -> dict:
        return {
            "detections": [
                {
                    "defect_class": d.defect_class,
                    "confidence": round(d.confidence, 4),
                    "severity": d.severity,
                    "severity_score": round(d.severity_score, 4),
                    "bbox": d.bbox,
                    "bbox_pixels": d.bbox_pixels,
                    "dimensions": d.dimensions,
                }
                for d in self.detections
            ],
            "detection_count": self.detection_count,
            "severity_summary": self.severity_summary,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "inference_time_ms": round(self.inference_time_ms, 2),
            "model_name": self.model_name,
        }


# Class name mapping (YOLO class index → name)
# Must match the order in data.yaml used during training.
CLASS_NAMES = {
    0: "crack",
    1: "spalling",
    2: "exposed_rebar",
    3: "corrosion",
    4: "efflorescence",
    5: "scaling",
    6: "honeycombing",
}

# Base severity weights per defect type (from defect_classes.json)
BASE_SEVERITY_WEIGHTS = {
    "crack": 0.6,
    "spalling": 0.7,
    "exposed_rebar": 0.9,
    "corrosion": 0.85,
    "efflorescence": 0.5,
    "scaling": 0.65,
    "honeycombing": 0.75,
}


def severity_from_score(score: float) -> str:
    """Convert a 0-1 severity score to a severity level."""
    if score >= 0.75:
        return "critical"
    elif score >= 0.5:
        return "high"
    elif score >= 0.25:
        return "medium"
    else:
        return "low"


class DefectDetector:
    """End-to-end defect detection pipeline.

    Loads a YOLOv11 model for detection and optionally a ResNet-18 model
    for severity classification. If no severity model is available, severity
    is estimated using a rule-based algorithm based on defect type and size.
    """

    def __init__(
        self,
        detector_path: str | Path,
        severity_model_path: str | Path | None = None,
        device: str = "cpu",
        confidence_threshold: float = 0.25,
    ):
        import time

        self.device = device
        self.confidence_threshold = confidence_threshold

        # Load YOLO detector
        logger.info(f"Loading YOLO detector from {detector_path}")
        start = time.time()
        try:
            from ultralytics import YOLO
            self.yolo = YOLO(str(detector_path))
            logger.info(f"YOLO loaded in {(time.time() - start) * 1000:.0f}ms")
        except Exception as e:
            logger.warning(f"Could not load YOLO model: {e}. Running in demo mode.")
            self.yolo = None

        # Load severity classifier (optional)
        self.severity_model = None
        self.severity_transforms = None
        if severity_model_path and Path(severity_model_path).exists():
            try:
                from torchvision import transforms

                checkpoint = torch.load(
                    str(severity_model_path), map_location=device, weights_only=True
                )
                from ml.training.train_severity import build_model

                self.severity_model = build_model(num_classes=4, pretrained=False)
                self.severity_model.load_state_dict(checkpoint["model_state_dict"])
                self.severity_model.to(device)
                self.severity_model.eval()

                self.severity_transforms = transforms.Compose([
                    transforms.Resize(int(224 * 1.15)),
                    transforms.CenterCrop(224),
                    transforms.ToTensor(),
                    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
                ])
                logger.info("Severity classifier loaded successfully.")
            except Exception as e:
                logger.warning(f"Could not load severity model: {e}. Using rule-based severity.")
        else:
            logger.info("No severity model found. Using rule-based severity estimation.")

    def predict(self, image: Image.Image) -> InferenceResult:
        """Run full detection + severity pipeline on a single PIL Image.

        Args:
            image: PIL Image (RGB).

        Returns:
            InferenceResult with all detections and severity grades.
        """
        import time

        start = time.time()
        w, h = image.size
        result = InferenceResult(image_width=w, image_height=h)

        if self.yolo is None:
            # Demo mode — return synthetic detections for testing the UI
            result.detections = self._generate_demo_detections(w, h)
            result.inference_time_ms = (time.time() - start) * 1000
            result.model_name = "demo"
            return result

        # Run YOLO detection
        yolo_results = self.yolo(
            image,
            conf=self.confidence_threshold,
            device=self.device,
            verbose=False,
        )

        if not yolo_results or len(yolo_results) == 0:
            result.inference_time_ms = (time.time() - start) * 1000
            result.model_name = self.yolo.model_name if hasattr(self.yolo, "model_name") else "yolo"
            return result

        boxes = yolo_results[0].boxes
        if boxes is None or len(boxes) == 0:
            result.inference_time_ms = (time.time() - start) * 1000
            return result

        # Process each detection
        for box in boxes:
            cls_id = int(box.cls[0].item())
            confidence = float(box.conf[0].item())
            x1, y1, x2, y2 = box.xyxy[0].tolist()

            defect_class = CLASS_NAMES.get(cls_id, f"unknown_{cls_id}")
            bbox_w = x2 - x1
            bbox_h = y2 - y1

            # Calculate severity
            severity_score = self._calculate_severity(
                image, defect_class, confidence, x1, y1, x2, y2, w, h
            )

            detection = DetectionResult(
                defect_class=defect_class,
                confidence=confidence,
                severity=severity_from_score(severity_score),
                severity_score=severity_score,
                bbox={
                    "x": round(x1 / w, 4),
                    "y": round(y1 / h, 4),
                    "w": round(bbox_w / w, 4),
                    "h": round(bbox_h / h, 4),
                },
                bbox_pixels={
                    "x1": round(x1),
                    "y1": round(y1),
                    "x2": round(x2),
                    "y2": round(y2),
                },
                dimensions={
                    "width_px": round(bbox_w),
                    "height_px": round(bbox_h),
                    "area_px": round(bbox_w * bbox_h),
                },
            )
            result.detections.append(detection)

        result.inference_time_ms = (time.time() - start) * 1000
        result.model_name = "yolo11"
        return result

    def predict_from_bytes(self, image_bytes: bytes) -> InferenceResult:
        """Run prediction from raw image bytes."""
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return self.predict(image)

    def _calculate_severity(
        self,
        image: Image.Image,
        defect_class: str,
        confidence: float,
        x1: float, y1: float, x2: float, y2: float,
        img_w: int, img_h: int,
    ) -> float:
        """Calculate severity score using ML model or rule-based fallback.

        Multi-factor scoring:
            - Defect type (25%): base severity weight from defect taxonomy
            - Area ratio (25%): defect area relative to image area
            - Confidence (20%): higher confidence → more visible → potentially worse
            - Aspect ratio (15%): elongated defects (cracks) scored differently
            - Edge proximity (15%): defects near edges may indicate structural issues
        """
        # Try ML-based severity first
        if self.severity_model is not None:
            try:
                crop = image.crop((int(x1), int(y1), int(x2), int(y2)))
                tensor = self.severity_transforms(crop).unsqueeze(0).to(self.device)
                with torch.no_grad():
                    output = self.severity_model(tensor)
                    probs = torch.softmax(output, dim=1)[0]
                # Weighted score: low=0.125, medium=0.375, high=0.625, critical=0.875
                weights = torch.tensor([0.125, 0.375, 0.625, 0.875]).to(self.device)
                return float((probs * weights).sum().item())
            except Exception as e:
                logger.warning(f"Severity model inference failed: {e}. Falling back to rules.")

        # Rule-based severity estimation
        base_weight = BASE_SEVERITY_WEIGHTS.get(defect_class, 0.5)

        # Area ratio — larger defects are more severe
        defect_area = (x2 - x1) * (y2 - y1)
        image_area = img_w * img_h
        area_ratio = min(defect_area / image_area, 1.0)
        area_score = min(area_ratio * 10, 1.0)  # Normalize: 10% of image = max

        # Confidence factor — higher confidence suggests a more prominent defect
        conf_score = confidence

        # Aspect ratio — very elongated defects (long cracks) score higher
        bbox_w = x2 - x1
        bbox_h = y2 - y1
        aspect = max(bbox_w, bbox_h) / max(min(bbox_w, bbox_h), 1)
        aspect_score = min(aspect / 10, 1.0)

        # Edge proximity — defects near image edges may indicate spreading
        cx = (x1 + x2) / 2 / img_w
        cy = (y1 + y2) / 2 / img_h
        edge_dist = min(cx, 1 - cx, cy, 1 - cy)
        edge_score = 1.0 - min(edge_dist * 4, 1.0)

        # Weighted combination
        severity_score = (
            base_weight * 0.25
            + area_score * 0.25
            + conf_score * 0.20
            + aspect_score * 0.15
            + edge_score * 0.15
        )
        return max(0.0, min(1.0, severity_score))

    def _generate_demo_detections(self, w: int, h: int) -> list[DetectionResult]:
        """Generate synthetic detections for demo/testing when no model is loaded."""
        import random

        demos = [
            ("crack", 0.92, 0.15, 0.3, 0.45, 0.35),
            ("spalling", 0.87, 0.55, 0.2, 0.75, 0.45),
            ("exposed_rebar", 0.78, 0.1, 0.6, 0.35, 0.85),
        ]
        results = []
        for cls, conf, nx1, ny1, nx2, ny2 in demos:
            x1, y1, x2, y2 = nx1 * w, ny1 * h, nx2 * w, ny2 * h
            bbox_w, bbox_h = x2 - x1, y2 - y1
            sev_score = random.uniform(0.2, 0.9)
            results.append(DetectionResult(
                defect_class=cls,
                confidence=conf,
                severity=severity_from_score(sev_score),
                severity_score=sev_score,
                bbox={"x": round(nx1, 4), "y": round(ny1, 4), "w": round((nx2 - nx1), 4), "h": round((ny2 - ny1), 4)},
                bbox_pixels={"x1": round(x1), "y1": round(y1), "x2": round(x2), "y2": round(y2)},
                dimensions={"width_px": round(bbox_w), "height_px": round(bbox_h), "area_px": round(bbox_w * bbox_h)},
            ))
        return results
