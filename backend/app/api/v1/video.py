from app.services.inspections import record_inspection
from app.services.uploads import stream_upload, project_directory, upload_url
from app.services.video_results import save_result, get_result
from app.services.runtime import run_blocking
from app.services.access import project_access, model_access, assignee_access, invalidate_calibration
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
    frame_skip: int = Form(default=10, ge=1, le=300, description="Process every Nth frame (higher = faster, lower = more thorough)"),
    auto_save: bool = Form(default=True, description="Auto-save detected defects to project"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Upload a video file, process it frame-by-frame with YOLOv11, and return results.

    The video is analyzed by sampling every Nth frame (default: every 10th).
    Duplicate defects across frames are merged using IoU overlap.
    An annotated output video with bounding boxes is generated.
    """
    await project_access(project_id, user, db)
    _validate_video_file(file)

    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[3]

    video_path, _ = await stream_upload(file, project_id, "videos", MAX_VIDEO_SIZE, ALLOWED_VIDEO_EXTENSIONS)
    output_dir = project_directory(project_id, "videos/annotated")

    # Process video in a thread to avoid blocking the event loop
    await project_access(project_id, user, db)
    detector = get_detector()

    from ml.inference.video_processor import process_video_file
    loop = asyncio.get_event_loop()
    result = await run_blocking(
        lambda: process_video_file(
            video_path=str(video_path),
            detector=detector,
            frame_skip=frame_skip,
            output_dir=str(output_dir),
            generate_annotated=True,
        ),
    )

    # Generate a result ID for retrieval
    result_id = uuid.uuid4().hex

    # Build response
    response_data = result.to_dict()

    # Convert annotated video path to a download URL
    if result.annotated_video_path:
        response_data["annotated_video_url"] = upload_url(result.annotated_video_path)
        response_data["download_url"] = f"/api/v1/video/download/{result_id}"

    inspection_id = record_inspection(db, project_id, user.id, "Video inspection") if auto_save else None
    saved_defects = []
    if auto_save:
        for fd in result.frame_detections:
            for det in fd.detections:
                defect = Defect(id=uuid.uuid4(), project_id=uuid.UUID(project_id), inspection_id=inspection_id,
                    defect_class=DefectClass(det.defect_class), severity=SeverityLevel(det.severity),
                    severity_score=det.severity_score, confidence=det.confidence, bbox=det.bbox,
                    source_image_url=getattr(fd, "snapshot_url", upload_url(video_path)),
                    status=DefectStatus.DETECTED, created_by_id=user.id,
                    notes=f"Video observation at {fd.timestamp_ms/1000:.1f}s; physical identity unverified")
                db.add(defect)
                saved_defects.append(str(defect.id))
        await db.flush()

    response_data["result_id"] = result_id
    response_data["saved_defect_count"] = len(saved_defects)
    response_data["source_video_url"] = upload_url(video_path)

    save_result(result_id, project_id, response_data, result.annotated_video_path)

    return response_data


@router.get("/download/{result_id}")
async def download_annotated_video(
    result_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Download the annotated video file for a processed result."""
    cached = await get_result(result_id, user, db)
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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Retrieve cached results for a previously processed video."""
    cached = await get_result(result_id, user, db)
    if not cached:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Video results not found. They may have expired.")
    return cached["data"]


@router.post("/stream/analyze")
async def analyze_rtsp_stream(
    rtsp_url: str = Form(..., description="RTSP stream URL (e.g., rtsp://user:pass@ip:554/stream)"),
    project_id: str = Form(..., description="Project UUID"),
    frame_skip: int = Form(default=15, ge=1, le=300, description="Process every Nth frame"),
    db: AsyncSession = Depends(get_db),
    max_frames: int = Form(default=100, ge=1, le=300, description="Max frames to process before stopping"),
    user: User = Depends(get_current_active_user),
):
    """Connect to an RTSP/CCTV stream, process frames, and return aggregated results.

    This endpoint processes up to max_frames sampled frames from the stream,
    then returns the aggregated detection results.
    """
    await project_access(project_id, user, db)
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
            raise

        from ml.inference.video_processor import _deduplicate_detections
        result.unique_defects = result.total_detections
        return result

    result = await run_blocking(_process)

    response = result.to_dict()
    response["status"] = "completed"

    return response
