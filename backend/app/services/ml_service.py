"""ML Service — singleton model loader and inference wrapper.

Manages the lifecycle of the YOLO detector and severity classifier.
Provides a clean interface for the API layer to run inference without
worrying about model loading, device management, or error handling.
"""

import logging
from threading import Lock
import uuid
from pathlib import Path

from PIL import Image

from app.core.config import get_settings
from ml.inference.detector import DefectDetector, InferenceResult
from ml.inference.postprocessor import annotate_image, image_to_bytes

logger = logging.getLogger(__name__)

# Singleton detector instance (loaded once, reused across requests)
_detector: DefectDetector | None = None
_load_lock = Lock()


def get_detector() -> DefectDetector:
    with _load_lock:
        return _load_detector()

def _load_detector() -> DefectDetector:
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
    from app.services.runtime import run_blocking
    return await run_blocking(lambda: get_detector().predict(_decode_image(image_bytes)))


def _decode_image(image_bytes):
    import io
    from app.core.exceptions import ValidationError
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.width * image.height > get_settings().MAX_IMAGE_PIXELS:
            raise ValidationError("Image resolution exceeds the pixel limit")
        image.load()
        from PIL import ImageOps
        return ImageOps.exif_transpose(image).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValidationError("Invalid image") from exc


async def run_inference_and_annotate(image_bytes: bytes) -> tuple[InferenceResult, bytes]:
    from app.services.runtime import run_blocking
    def work():
        image = _decode_image(image_bytes)
        result = get_detector().predict(image)
        return result, image_to_bytes(annotate_image(image, result))
    return await run_blocking(work)


async def save_uploaded_file(file_bytes: bytes, filename: str,
                             subfolder: str = "inspections", *, project_id) -> str:
    from app.services.uploads import project_directory, upload_url
    folder = project_directory(project_id, subfolder)
    ext = Path(filename).suffix.lower() or ".jpg"
    path = folder / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(file_bytes)
    return upload_url(path)
