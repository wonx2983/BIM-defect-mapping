"""Explicit RTSP transport policy and bounded OpenCV capture."""
import ipaddress
from urllib.parse import urlsplit
import cv2
from app.core.config import get_settings
from app.core.exceptions import ValidationError, AppException


def validate_stream_url(value):
    try:
        url = urlsplit(value)
        port = url.port
    except (TypeError, ValueError):
        raise ValidationError("Invalid camera URL")
    if url.scheme not in {"rtsp", "rtsps"} or not url.hostname or url.fragment:
        raise ValidationError("Camera URL must use rtsp:// or rtsps://")
    settings = get_settings()
    allowed = {host.strip().lower() for host in settings.CAMERA_ALLOWED_HOSTS.split(",") if host.strip()}
    if settings.APP_ENV == "production" and not allowed:
        raise ValidationError("Configure CAMERA_ALLOWED_HOSTS before connecting cameras")
    if allowed and url.hostname.lower() not in allowed:
        raise ValidationError("Camera host is not in CAMERA_ALLOWED_HOSTS")
    try:
        address = ipaddress.ip_address(url.hostname)
        if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified:
            raise ValidationError("Camera address is not allowed")
    except ValueError:
        if url.hostname.lower() in {"localhost", "metadata.google.internal"}:
            raise ValidationError("Camera address is not allowed")
    return value


def open_stream(url):
    validate_stream_url(url)
    timeout = get_settings().STREAM_TIMEOUT_SECONDS * 1000
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout,
    ])
    if not cap.isOpened():
        cap.release()
        raise AppException("Camera connection failed", "CAMERA_UNAVAILABLE", 502)
    return cap
