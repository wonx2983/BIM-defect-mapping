"""Import all models so Alembic can detect schema changes."""

from app.db.session import Base  # noqa: F401
from app.models import (  # noqa: F401
    Organization,
    User,
    Project,
    BIMModel,
    Inspection,
    Defect,
)
