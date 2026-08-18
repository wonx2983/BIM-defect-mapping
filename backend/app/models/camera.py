"""Camera model — CCTV/IP cameras registered to BIM elements for auto-mapping."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class CameraStatus(str, enum.Enum):
    """Camera operational status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class Camera(Base):
    """Registered CCTV/IP camera linked to a BIM element or zone.

    When defects are detected from this camera's RTSP feed, they are
    automatically mapped to the linked BIM element and 3D position.
    """

    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(255))
    rtsp_url: Mapped[str] = mapped_column(String(1024))

    # BIM mapping — what part of the building does this camera watch?
    bim_model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bim_models.id"), nullable=True
    )
    bim_element_guid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bim_zone_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    world_position: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {x, y, z}

    # Camera metadata
    location_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CameraStatus] = mapped_column(
        Enum(CameraStatus), default=CameraStatus.ACTIVE
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    frame_skip: Mapped[int] = mapped_column(Integer, default=15)

    # Scheduling
    auto_detect_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_detect_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    last_detection_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_defects_found: Mapped[int] = mapped_column(Integer, default=0)

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project: Mapped["Project"] = relationship(foreign_keys=[project_id])  # noqa: F821
    bim_model: Mapped["BIMModel | None"] = relationship(foreign_keys=[bim_model_id])  # noqa: F821
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])  # noqa: F821

    def __repr__(self) -> str:
        return f"<Camera(id={self.id}, name={self.name}, zone={self.bim_zone_label})>"
