"""Durable, bounded-lifetime result manifests shared by local-volume workers."""
import json
import re
import time
import uuid
from app.services.uploads import upload_root
from app.services.access import project_access
from app.core.exceptions import NotFoundError


def save_result(result_id, project_id, data, annotated_path):
    root = upload_root() / ".results"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{result_id}.json"
    temporary = root / f"{uuid.uuid4().hex}.tmp"
    temporary.write_text(json.dumps({"project_id": str(project_id), "created": time.time(),
        "data": data, "annotated_video_path": annotated_path}), encoding="utf-8")
    temporary.replace(target)


async def get_result(result_id, user, db):
    if not re.fullmatch(r"[0-9a-f]{32}", result_id):
        raise NotFoundError("Video result not found")
    path = upload_root() / ".results" / f"{result_id}.json"
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise NotFoundError("Video result not found")
    await project_access(result["project_id"], user, db)
    if time.time() - result["created"] > 7 * 86400:
        raise NotFoundError("Video result expired")
    return result
