"""ArUco fiducial marker detection using OpenCV.

Detects ArUco markers in a camera frame and returns their corner pixel
coordinates and decoded IDs.  This is the first step of the calibration
pipeline: the detected corners are fed into ``solvePnP`` to recover the
camera's 3D pose.

Supports multiple ArUco dictionaries (4×4, 5×5, 6×6, 7×7 in various
sizes).  The default is ``DICT_4X4_50`` which is recommended for
construction sites due to its large, high-contrast patterns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Mapping from string names to OpenCV ArUco dictionary constants.
ARUCO_DICT_MAP: dict[str, int] = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
    "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
    "DICT_5X5_1000": cv2.aruco.DICT_5X5_1000,
    "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
    "DICT_6X6_100": cv2.aruco.DICT_6X6_100,
    "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
    "DICT_6X6_1000": cv2.aruco.DICT_6X6_1000,
    "DICT_7X7_50": cv2.aruco.DICT_7X7_50,
    "DICT_7X7_100": cv2.aruco.DICT_7X7_100,
    "DICT_7X7_250": cv2.aruco.DICT_7X7_250,
    "DICT_7X7_1000": cv2.aruco.DICT_7X7_1000,
}


@dataclass(frozen=True)
class DetectedMarker:
    """A single detected ArUco marker in a camera frame.

    Attributes:
        marker_id: The decoded integer ID from the marker pattern.
        corners: 4×2 numpy array of corner pixel coordinates in order:
                 [top-left, top-right, bottom-right, bottom-left].
        centre: (x, y) pixel coordinate of the marker's centre.
    """

    marker_id: int
    corners: np.ndarray  # shape (4, 2), dtype float32
    centre: tuple[float, float]


def detect_markers(
    frame: np.ndarray,
    dict_type: str = "DICT_4X4_50",
) -> list[DetectedMarker]:
    """Detect all ArUco markers in a BGR frame.

    Args:
        frame: BGR image (numpy array from OpenCV).
        dict_type: ArUco dictionary name (must be a key in ``ARUCO_DICT_MAP``).

    Returns:
        List of ``DetectedMarker`` instances found in the frame.  Empty list
        if no markers are detected.

    Raises:
        ValueError: If ``dict_type`` is not a recognised ArUco dictionary.
    """
    if dict_type not in ARUCO_DICT_MAP:
        raise ValueError(
            f"Unknown ArUco dictionary '{dict_type}'. "
            f"Supported: {sorted(ARUCO_DICT_MAP.keys())}"
        )

    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT_MAP[dict_type])
    params = cv2.aruco.DetectorParameters()
    # Tune for construction-site conditions: variable lighting, dust on markers.
    params.adaptiveThreshWinSizeMin = 3
    params.adaptiveThreshWinSizeMax = 23
    params.adaptiveThreshWinSizeStep = 10
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    params.cornerRefinementMaxIterations = 50

    detector = cv2.aruco.ArucoDetector(aruco_dict, params)
    corners_list, ids, _rejected = detector.detectMarkers(frame)

    if ids is None or len(ids) == 0:
        logger.debug("No ArUco markers detected in frame")
        return []

    results: list[DetectedMarker] = []
    for i, marker_id in enumerate(ids.flatten()):
        corners = corners_list[i].reshape(4, 2).astype(np.float32)
        cx = float(corners[:, 0].mean())
        cy = float(corners[:, 1].mean())
        results.append(DetectedMarker(
            marker_id=int(marker_id),
            corners=corners,
            centre=(cx, cy),
        ))

    logger.info("Detected %d ArUco marker(s): %s", len(results),
                [m.marker_id for m in results])
    return results


def grab_frame_from_rtsp(rtsp_url: str, timeout_sec: float = 10.0) -> np.ndarray:
    """Grab a single frame from an RTSP stream.

    Args:
        rtsp_url: The RTSP URL to connect to.
        timeout_sec: How long to wait for a frame before raising.

    Returns:
        BGR frame as a numpy array.

    Raises:
        RuntimeError: If the stream cannot be opened or no frame is received.
    """
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open RTSP stream: {rtsp_url}")

    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(timeout_sec * 1000))

    # Read a few frames to skip initial buffered/stale frames.
    for _ in range(5):
        ret, frame = cap.read()

    cap.release()

    if not ret or frame is None:
        raise RuntimeError(f"No frame received from RTSP stream: {rtsp_url}")

    logger.info("Grabbed frame from RTSP: %s, shape=%s", rtsp_url, frame.shape)
    return frame
