"""Shared authorization and project-bound resource checks."""
import uuid
from sqlalchemy import select
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.project import Project
from app.models.bim_model import BIMModel
from app.models.user import User, UserRole


async def project_access(project_id, user, db):
    try:
        project_id = uuid.UUID(str(project_id))
    except (ValueError, TypeError):
        raise ValidationError("Invalid project ID")
    project = await db.scalar(select(Project).where(Project.id == project_id))
    if project is None or project.organization_id != user.organization_id:
        raise NotFoundError("Project not found")
    return project


async def model_access(model_id, project_id, db):
    if model_id is None:
        return None
    model = await db.scalar(select(BIMModel).where(
        BIMModel.id == model_id, BIMModel.project_id == project_id))
    if model is None:
        raise ValidationError("BIM model does not belong to this project")
    return model


async def assignee_access(user_id, user, db):
    if user_id is not None:
        assignee = await db.scalar(select(User).where(
            User.id == user_id, User.organization_id == user.organization_id,
            User.is_active.is_(True)))
        if assignee is None:
            raise ValidationError("Assignee must be an active member of your organization")


def invalidate_calibration(camera):
    camera.auto_detect_enabled = False
    camera.calibration_status = "uncalibrated"
    camera.pose_rotation = camera.pose_translation = None
    camera.candidate_element_guids = None
    camera.calibrated_at = camera.calibration_error_px = None
