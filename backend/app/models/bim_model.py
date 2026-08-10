"""BIM Model (IFC file) model."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ProcessingStatus(str, enum.Enum):
    """IFC file processing pipeline status."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class BIMModel(Base):
    """Uploaded IFC/BIM model with server-side processing status."""

    __tablename__ = "bim_models"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    original_filename: Mapped[str] = mapped_column(String(512))
    file_url: Mapped[str] = mapped_column(String(1024))
    fragment_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus), default=ProcessingStatus.UPLOADED
    )
    element_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="bim_models")  # noqa: F821
    uploaded_by: Mapped["User"] = relationship(foreign_keys=[uploaded_by_id])  # noqa: F821

    def __repr__(self) -> str:
        return f"<BIMModel(id={self.id}, filename={self.original_filename})>"
