"""User model."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class UserRole(str, enum.Enum):
    """User role within an organization."""

    ADMIN = "admin"
    MANAGER = "manager"
    INSPECTOR = "inspector"
    VIEWER = "viewer"


class User(Base):
    """Application user with role-based access."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(1024))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.INSPECTOR)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="users")  # noqa: F821
    defects_created: Mapped[list["Defect"]] = relationship(  # noqa: F821
        back_populates="created_by", foreign_keys="[Defect.created_by_id]"
    )
    assigned_defects: Mapped[list["Defect"]] = relationship(  # noqa: F821
        back_populates="assigned_to", foreign_keys="[Defect.assigned_to_id]"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
