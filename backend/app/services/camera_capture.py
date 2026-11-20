"""Capture evidence and retain the resolution used for each observation."""
import time
import uuid
import cv2
from app.core.exceptions import ValidationError
from app.services.uploads import project_directory, upload_url
from ml.inference.video_processor import process_rtsp_frames
from ml.inference.video_tracks import FrameDetection


def capture_observations(camera, detector, max_frames):
    observations = []
    started = time.monotonic()
    for index, inference, annotated in process_rtsp_frames(
            camera.rtsp_url, detector, camera.frame_skip, max_frames):
        if camera.calibration_status == "calibrated" and (
                inference.image_width != camera.image_width or inference.image_height != camera.image_height):
            raise ValidationError("Stream resolution changed; recalibrate the camera")
        frame = FrameDetection(index, (time.monotonic() - started) * 1000,
                               inference.detections, inference.inference_time_ms)
        if inference.detections:
            path = project_directory(camera.project_id, "camera-evidence") / f"{uuid.uuid4().hex}.jpg"
            if not cv2.imwrite(str(path), annotated):
                raise RuntimeError("Could not write camera evidence")
            frame.snapshot_url = upload_url(path)
        observations.append(frame)
    return observations
