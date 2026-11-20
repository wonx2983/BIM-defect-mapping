"""Private project media. JWT cookies are accepted only for read-only assets."""
import uuid
from pathlib import Path
from fastapi import APIRouter, Request, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select, or_
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.bim_model import BIMModel
from app.models.defect import Defect
from app.services.access import project_access
from app.services.uploads import upload_root
from app.core.exceptions import NotFoundError, UnauthorizedError

router = APIRouter(tags=["Private media"])


@router.get("/uploads/{asset:path}")
async def media(asset: str, request: Request, db=Depends(get_db)):
    authorization = request.headers.get("authorization")
    if not authorization:
        token = request.cookies.get("defectsync_media")
        if not token:
            raise UnauthorizedError()
        authorization = f"Bearer {token}"
    user = await get_current_user(authorization=authorization, db=db)
    if not user.is_active:
        raise UnauthorizedError()
    root = upload_root()
    path = (root / asset).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix == ".json":
        raise NotFoundError("Asset not found")
    parts = Path(asset).parts
    if len(parts) >= 3 and parts[0] == "projects":
        await project_access(parts[1], user, db)
    else:
        # Existing installations: authorize legacy paths by their owning DB record.
        url = "/uploads/" + Path(asset).as_posix()
        project_id = await db.scalar(select(BIMModel.project_id).where(BIMModel.file_url == url))
        if project_id is None:
            project_id = await db.scalar(select(Defect.project_id).where(or_(
                Defect.source_image_url == url, Defect.annotated_image_url == url)).limit(1))
        if project_id is None:
            raise NotFoundError("Asset not found")
        await project_access(project_id, user, db)
    return FileResponse(path, headers={"Cache-Control": "private, no-store",
                                     "X-Content-Type-Options": "nosniff"})
