"""Video detection endpoints — upload videos, connect RTSP streams, process frames.

Endpoints:
    POST /api/v1/video/upload         — Upload video file → process → return results + annotated video
    POST /api/v1/video/stream/start   — Start RTSP stream processing (returns SSE events)
    GET  /api/v1/video/results/{id}   — Get cached results for a processed video
    GET  /api/v1/video/download/{id}  — Download annotated video file
"""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.defect import Defect, DefectClass, DefectStatus, SeverityLevel
from app.models.user import User
from app.services.ml_service import get_detector, save_uploaded_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/video", tags=["Video Detection"])

# In-memory cache for video processing results (production would use Redis)
_video_results: dict[str, dict] = {}

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv"}
MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500MB


def _validate_video_file(file: UploadFile) -> None:
    """Validate uploaded file is an allowed video type."""
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            from app.core.exceptions import ValidationError
            raise ValidationError(
                f"Unsupported video type '{ext}'. Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}"
            )


@router.post("/upload")
async def upload_and_process_video(
    file: UploadFile = File(..., description="Video file (MP4, AVI, MOV, etc.)"),
    project_id: str = Form(..., description="Project UUID to associate defects with"),
    frame_skip: int = Form(default=10, description="Process every Nth frame (higher = faster, lower = more thorough)"),
    auto_save: bool = Form(default=True, description="Auto-save detected defects to project"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Upload a video file, process it frame-by-frame with YOLOv11, and return results.

    The video is analyzed by sampling every Nth frame (default: every 10th).
    Duplicate defects across frames are merged using IoU overlap.
    An annotated output video with bounding boxes is generated.
    """
    _validate_video_file(file)

    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[3]

    # Save uploaded video to disk
    video_bytes = await file.read()
    video_dir = backend_root / settings.LOCAL_UPLOAD_DIR / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "video.mp4").suffix.lower()
    video_filename = f"{uuid.uuid4().hex}{ext}"
    video_path = video_dir / video_filename
    video_path.write_bytes(video_bytes)

    # Output directory for annotated video
    output_dir = backend_root / settings.LOCAL_UPLOAD_DIR / "videos" / "annotated"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process video in a thread to avoid blocking the event loop
    detector = get_detector()

    from ml.inference.video_processor import process_video_file
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: process_video_file(
            video_path=str(video_path),
            detector=detector,
            frame_skip=frame_skip,
            output_dir=str(output_dir),
            generate_annotated=True,
        ),
    )

    # Generate a result ID for retrieval
    result_id = uuid.uuid4().hex[:12]

    # Build response
    response_data = result.to_dict()

    # Convert annotated video path to a download URL
    if result.annotated_video_path:
        annotated_rel = Path(result.annotated_video_path).relative_to(backend_root)
        response_data["annotated_video_url"] = f"/{annotated_rel.as_posix()}"
        response_data["download_url"] = f"/api/v1/video/download/{result_id}"

    # Auto-save unique defects to the project
    saved_defects = []
    if auto_save and result.unique_defects > 0:
        # Get one representative detection per unique defect
        seen_defects: list[tuple[str, dict]] = []
        for fd in result.frame_detections:
            for det in fd.detections:
                is_dup = False
                for sc, sb in seen_defects:
                    if det.defect_class == sc:
                        from ml.inference.video_processor import _iou
                        if _iou(det.bbox_pixels, sb) > 0.5:
                            is_dup = True
                            break
                if not is_dup:
                    seen_defects.append((det.defect_class, det.bbox_pixels))

                    # Save to DB
                    try:
                        defect = Defect(
                            project_id=uuid.UUID(project_id),
                            defect_class=DefectClass(det.defect_class),
                            severity=SeverityLevel(det.severity),
                            severity_score=det.severity_score,
                            confidence=det.confidence,
                            bbox=det.bbox,
                            source_image_url=f"/{settings.LOCAL_UPLOAD_DIR}/videos/{video_filename}",
                            status=DefectStatus.DETECTED,
                            created_by_id=user.id,
                            notes=f"Detected from video at frame {fd.frame_index} ({fd.timestamp_ms/1000:.1f}s)",
                        )
                        db.add(defect)
                        saved_defects.append(str(defect.id))
                    except Exception as e:
                        logger.warning(f"Failed to save defect: {e}")

        if saved_defects:
            await db.commit()

    response_data["result_id"] = result_id
    response_data["saved_defect_count"] = len(saved_defects)
    response_data["source_video_url"] = f"/{settings.LOCAL_UPLOAD_DIR}/videos/{video_filename}"

    # Cache result for later download
    _video_results[result_id] = {
        "data": response_data,
        "annotated_video_path": result.annotated_video_path,
    }

    return response_data


@router.get("/download/{result_id}")
async def download_annotated_video(
    result_id: str,
    user: User = Depends(get_current_active_user),
):
    """Download the annotated video file for a processed result."""
    cached = _video_results.get(result_id)
    if not cached or not cached.get("annotated_video_path"):
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Annotated video not found. It may have expired.")

    path = Path(cached["annotated_video_path"])
    if not path.exists():
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Annotated video file not found on disk.")

    return FileResponse(
        path=str(path),
        media_type="video/mp4",
        filename=f"defectsync_annotated_{result_id}.mp4",
    )


@router.get("/results/{result_id}")
async def get_video_results(
    result_id: str,
    user: User = Depends(get_current_active_user),
):
    """Retrieve cached results for a previously processed video."""
    cached = _video_results.get(result_id)
    if not cached:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Video results not found. They may have expired.")
    return cached["data"]


@router.post("/stream/analyze")
async def analyze_rtsp_stream(
    rtsp_url: str = Form(..., description="RTSP stream URL (e.g., rtsp://user:pass@ip:554/stream)"),
    project_id: str = Form(..., description="Project UUID"),
    frame_skip: int = Form(default=15, description="Process every Nth frame"),
    max_frames: int = Form(default=100, description="Max frames to process before stopping"),
    user: User = Depends(get_current_active_user),
):
    """Connect to an RTSP/CCTV stream, process frames, and return aggregated results.

    This endpoint processes up to max_frames sampled frames from the stream,
    then returns the aggregated detection results.
    """
    detector = get_detector()

    from ml.inference.video_processor import process_rtsp_frames, VideoProcessingResult, FrameDetection

    loop = asyncio.get_event_loop()

    # Run RTSP processing in executor
    def _process():
        result = VideoProcessingResult(fps=0, duration_seconds=0)
        try:
            for frame_idx, inference, annotated in process_rtsp_frames(
                rtsp_url=rtsp_url,
                detector=detector,
                frame_skip=frame_skip,
                max_frames=max_frames,
            ):
                fd = FrameDetection(
                    frame_index=frame_idx,
                    timestamp_ms=0,
                    detections=inference.detections,
                    inference_time_ms=inference.inference_time_ms,
                )
                result.frame_detections.append(fd)
                result.processed_frames += 1
                result.total_detections += len(inference.detections)

                for det in inference.detections:
                    result.severity_summary[det.severity] = result.severity_summary.get(det.severity, 0) + 1
                    result.class_summary[det.defect_class] = result.class_summary.get(det.defect_class, 0) + 1
        except Exception as e:
            logger.error(f"RTSP processing error: {e}")

        from ml.inference.video_processor import _deduplicate_detections
        result.unique_defects = _deduplicate_detections(result.frame_detections)
        return result

    result = await loop.run_in_executor(None, _process)

    response = result.to_dict()
    response["stream_url"] = rtsp_url
    response["status"] = "completed"

    return response
