"""Inspection model."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class InspectionStatus(str, enum.Enum):
    """Inspection session status."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Inspection(Base):
    """Site inspection session containing detected defects."""

    __tablename__ = "inspections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    inspector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    zone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inspection_date: Mapped[date] = mapped_column(Date)
    status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus), default=InspectionStatus.IN_PROGRESS
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="inspections")  # noqa: F821
    inspector: Mapped["User"] = relationship(foreign_keys=[inspector_id])  # noqa: F821
    defects: Mapped[list["Defect"]] = relationship(back_populates="inspection")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Inspection(id={self.id}, title={self.title})>"
