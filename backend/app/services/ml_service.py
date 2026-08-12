"""ML Service — singleton model loader and inference wrapper.

Manages the lifecycle of the YOLO detector and severity classifier.
Provides a clean interface for the API layer to run inference without
worrying about model loading, device management, or error handling.
"""

import logging
import uuid
from pathlib import Path

from PIL import Image

from app.core.config import get_settings
from ml.inference.detector import DefectDetector, InferenceResult
from ml.inference.postprocessor import annotate_image, image_to_bytes

logger = logging.getLogger(__name__)

# Singleton detector instance (loaded once, reused across requests)
_detector: DefectDetector | None = None


def get_detector() -> DefectDetector:
    """Get or initialize the singleton DefectDetector.

    On first call, loads the YOLO model and (optionally) the severity
    classifier from disk. Subsequent calls return the cached instance.
    """
    global _detector
    if _detector is not None:
        return _detector

    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]

    detector_path = backend_root / settings.ML_MODEL_PATH
    severity_path = backend_root / "ml" / "models" / "severity_classifier.pt"

    logger.info(f"Initializing DefectDetector (device={settings.ML_DEVICE})")
    _detector = DefectDetector(
        detector_path=str(detector_path),
        severity_model_path=str(severity_path) if severity_path.exists() else None,
        device=settings.ML_DEVICE,
        confidence_threshold=settings.ML_CONFIDENCE_THRESHOLD,
    )
    return _detector


def reload_detector() -> DefectDetector:
    """Force-reload the detector (e.g., after training a new model)."""
    global _detector
    _detector = None
    return get_detector()


async def run_inference(image_bytes: bytes) -> InferenceResult:
    """Run defect detection on raw image bytes.

    Args:
        image_bytes: Raw image file content (JPEG, PNG, etc.)

    Returns:
        InferenceResult with all detections and severity grades.
    """
    detector = get_detector()
    return detector.predict_from_bytes(image_bytes)


async def run_inference_and_annotate(
    image_bytes: bytes,
) -> tuple[InferenceResult, bytes]:
    """Run detection and return both results and an annotated image.

    Args:
        image_bytes: Raw image file content.

    Returns:
        Tuple of (InferenceResult, annotated_image_bytes).
    """
    detector = get_detector()
    image = Image.open(
        __import__("io").BytesIO(image_bytes)
    ).convert("RGB")

    result = detector.predict(image)

    annotated = annotate_image(image, result)
    annotated_bytes = image_to_bytes(annotated)

    return result, annotated_bytes


async def save_uploaded_file(
    file_bytes: bytes,
    filename: str,
    subfolder: str = "inspections",
) -> str:
    """Save an uploaded file to local storage or S3.

    Returns the relative path/URL to the saved file.
    """
    settings = get_settings()

    if settings.is_local_storage:
        backend_root = Path(__file__).resolve().parents[2]
        upload_dir = backend_root / settings.LOCAL_UPLOAD_DIR / subfolder
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename to avoid collisions
        ext = Path(filename).suffix or ".jpg"
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = upload_dir / unique_name
        file_path.write_bytes(file_bytes)

        return f"/{settings.LOCAL_UPLOAD_DIR}/{subfolder}/{unique_name}"
    else:
        # S3 storage — would use boto3 here
        # For now, fall back to local
        logger.warning("S3 storage not implemented yet, using local storage.")
        return await save_uploaded_file(file_bytes, filename, subfolder)
