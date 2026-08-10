"""ORM models package — import all models here for Alembic discovery."""

from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.project import Project, ProjectStatus
from app.models.bim_model import BIMModel, ProcessingStatus
from app.models.inspection import Inspection, InspectionStatus
from app.models.defect import Defect, DefectClass, DefectStatus, SeverityLevel

__all__ = [
    "Organization",
    "User",
    "UserRole",
    "Project",
    "ProjectStatus",
    "BIMModel",
    "ProcessingStatus",
    "Inspection",
    "InspectionStatus",
    "Defect",
    "DefectClass",
    "DefectStatus",
    "SeverityLevel",
]
