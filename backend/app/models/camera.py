"""Camera model — CCTV/IP cameras registered to BIM elements for auto-mapping.

Supports two mapping modes:
  1. Simple mode (Phase 1): camera is linked to a single BIM element/zone.
  2. Calibrated mode (Phase 2): camera has a full 3D pose from PnP calibration,
     enabling automatic per-pixel defect-to-element mapping via raycasting.
"""

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


class CalibrationStatus(str, enum.Enum):
    """Camera calibration state."""

    UNCALIBRATED = "uncalibrated"
    CALIBRATING = "calibrating"
    CALIBRATED = "calibrated"
    FAILED = "failed"


class Camera(Base):
    """Registered CCTV/IP camera with optional PnP calibration for auto-mapping.

    When calibrated, the camera's intrinsics and extrinsics allow the system
    to convert any pixel coordinate into a 3D ray, which is then intersected
    against BIM element geometry to determine which element a defect belongs to.
    """

    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(255))
    rtsp_url: Mapped[str] = mapped_column(String(1024))

    # ── BIM mapping (simple mode — Phase 1) ──────────────────────────
    bim_model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bim_models.id"), nullable=True
    )
    bim_element_guid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bim_zone_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    world_position: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {x, y, z}

    # ── Camera intrinsics ────────────────────────────────────────────
    # Populated from camera datasheet (FOV) or formal checkerboard calibration.
    intrinsics: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Camera intrinsic params: {fx, fy, cx, cy, dist_coeffs?}",
    )
    fov_horizontal_deg: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Horizontal field of view in degrees (used to compute fx if intrinsics not set)",
    )
    image_width: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Frame width in pixels",
    )
    image_height: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Frame height in pixels",
    )

    # ── Camera extrinsics (from PnP calibration) ─────────────────────
    # Rotation: 3x3 matrix stored as flat list [r00, r01, ..., r22]
    pose_rotation: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="3x3 rotation matrix as {matrix: [9 floats], rvec: [3 floats]}",
    )
    # Translation: camera position in BIM world coordinates
    pose_translation: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Translation vector: {x, y, z} in BIM world coords",
    )

    # ── Calibration metadata ─────────────────────────────────────────
    calibration_status: Mapped[str] = mapped_column(
        String(32), default="uncalibrated",
        comment="uncalibrated | calibrating | calibrated | failed",
    )
    calibration_error_px: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Mean reprojection error in pixels from PnP solve",
    )
    calibrated_with_marker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fiducial_markers.id"), nullable=True,
    )
    calibrated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Candidate element set ────────────────────────────────────────
    # GUIDs of BIM elements inside this camera's view frustum.
    # Computed automatically after calibration; raycasting is restricted to this set.
    candidate_element_guids: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="List of BIM element GUIDs within this camera's view frustum",
    )

    # ── Camera metadata ──────────────────────────────────────────────
    location_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CameraStatus] = mapped_column(
        Enum(CameraStatus), default=CameraStatus.ACTIVE
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    frame_skip: Mapped[int] = mapped_column(Integer, default=15)

    # ── Scheduling ───────────────────────────────────────────────────
    auto_detect_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_detect_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    last_detection_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_defects_found: Mapped[int] = mapped_column(Integer, default=0)

    # ── Audit ────────────────────────────────────────────────────────
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
    calibration_marker: Mapped["FiducialMarker | None"] = relationship(  # noqa: F821
        foreign_keys=[calibrated_with_marker_id],
    )

    @property
    def is_calibrated(self) -> bool:
        """Whether this camera has a valid PnP calibration."""
        return (
            self.calibration_status == "calibrated"
            and self.pose_rotation is not None
            and self.pose_translation is not None
            and self.intrinsics is not None
        )

    def __repr__(self) -> str:
        cal = "calibrated" if self.is_calibrated else "uncalibrated"
        return f"<Camera(id={self.id}, name={self.name}, {cal})>"
