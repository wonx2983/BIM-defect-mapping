"""Defect model — the core entity for detected construction defects."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DefectClass(str, enum.Enum):
    """Classification of structural defect type."""

    CRACK = "crack"
    SPALLING = "spalling"
    EXPOSED_REBAR = "exposed_rebar"
    CORROSION = "corrosion"
    EFFLORESCENCE = "efflorescence"
    SCALING = "scaling"
    HONEYCOMBING = "honeycombing"


class SeverityLevel(str, enum.Enum):
    """4-tier severity grading."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DefectStatus(str, enum.Enum):
    """Defect lifecycle status."""

    DETECTED = "detected"
    CONFIRMED = "confirmed"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    VERIFIED = "verified"


class Defect(Base):
    """Detected construction defect with classification, severity, and BIM mapping."""

    __tablename__ = "defects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    inspection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inspections.id"), nullable=True
    )
    bim_element_guid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    defect_class: Mapped[DefectClass] = mapped_column(Enum(DefectClass))
    severity: Mapped[SeverityLevel] = mapped_column(Enum(SeverityLevel))
    severity_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    bbox: Mapped[dict] = mapped_column(JSON)  # {x, y, w, h}
    source_image_url: Mapped[str] = mapped_column(String(1024))
    annotated_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    world_position: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {x, y, z}
    dimensions: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )  # {width_mm, height_mm, area_mm2}
    status: Mapped[DefectStatus] = mapped_column(
        Enum(DefectStatus), default=DefectStatus.DETECTED
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="defects")  # noqa: F821
    inspection: Mapped["Inspection | None"] = relationship(back_populates="defects")  # noqa: F821
    assigned_to: Mapped["User | None"] = relationship(  # noqa: F821
        back_populates="assigned_defects", foreign_keys=[assigned_to_id]
    )
    created_by: Mapped["User"] = relationship(  # noqa: F821
        back_populates="defects_created", foreign_keys=[created_by_id]
    )

    def __repr__(self) -> str:
        return f"<Defect(id={self.id}, class={self.defect_class}, severity={self.severity})>"
