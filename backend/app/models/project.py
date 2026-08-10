"""Project model."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ProjectStatus(str, enum.Enum):
    """Project lifecycle status."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Project(Base):
    """Construction project containing inspections, BIM models, and defects."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="projects")  # noqa: F821
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])  # noqa: F821
    bim_models: Mapped[list["BIMModel"]] = relationship(back_populates="project")  # noqa: F821
    inspections: Mapped[list["Inspection"]] = relationship(back_populates="project")  # noqa: F821
    defects: Mapped[list["Defect"]] = relationship(back_populates="project")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name={self.name})>"
