"""Bounded uploads and project-scoped local storage."""
import uuid
from pathlib import Path
from app.core.config import get_settings
from app.core.exceptions import ValidationError


def upload_root():
    return (Path(__file__).resolve().parents[2] / get_settings().LOCAL_UPLOAD_DIR).resolve()


def project_directory(project_id, category):
    project_root = upload_root() / "projects" / str(uuid.UUID(str(project_id)))
    root = (project_root / category).resolve()
    if not root.is_relative_to(project_root):
        raise ValidationError("Invalid storage category")
    root.mkdir(parents=True, exist_ok=True)
    return root


def upload_url(path):
    return "/uploads/" + Path(path).resolve().relative_to(upload_root()).as_posix()


async def read_bounded(file, limit):
    data = bytearray()
    while chunk := await file.read(min(1024 * 1024, limit + 1 - len(data))):
        data.extend(chunk)
        if len(data) > limit:
            raise ValidationError(f"Upload exceeds {limit // (1024 * 1024)} MB")
    if not data:
        raise ValidationError("Empty upload")
    return bytes(data)


async def stream_upload(file, project_id, category, limit, extensions):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in extensions:
        raise ValidationError("Unsupported file extension")
    target = project_directory(project_id, category) / f"{uuid.uuid4().hex}{ext}"
    size = 0
    try:
        with target.open("wb") as stream:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise ValidationError(f"Upload exceeds {limit // (1024 * 1024)} MB")
                stream.write(chunk)
        if not size:
            raise ValidationError("Empty upload")
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target, size
