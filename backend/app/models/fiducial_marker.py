"""Fiducial marker model — ArUco markers registered at known BIM coordinates.

Each marker anchors a printed ArUco pattern to a precise 3D coordinate
already present in the BIM model.  During camera calibration the marker's
known world position is combined with its detected pixel corners to solve
for the camera's pose via PnP.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class FiducialMarker(Base):
    """A physical ArUco marker placed at a known BIM coordinate.

    The marker registry is a small lookup table: each row maps a unique
    ArUco dictionary ID to the 3D coordinate where the marker is taped
    on the real structure.  The coordinate is read directly from the BIM
    model (the same data the viewer already uses to render elements).
    """

    __tablename__ = "fiducial_markers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))

    # ArUco marker identity
    marker_dict_id: Mapped[int] = mapped_column(
        Integer,
        comment="ArUco marker ID decoded from the printed pattern",
    )
    aruco_dict_type: Mapped[str] = mapped_column(
        String(64),
        default="DICT_4X4_50",
        comment="OpenCV ArUco dictionary name (e.g. DICT_4X4_50, DICT_6X6_250)",
    )

    # Where the marker is placed (BIM reference)
    bim_model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bim_models.id"), nullable=True,
    )
    bim_element_guid: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="GUID of the BIM element the marker is attached to",
    )
    bim_point_description: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Human-readable description, e.g. 'Column A12, top-left corner'",
    )

    # 3D coordinate in the BIM world coordinate system
    world_x: Mapped[float] = mapped_column(Float, comment="X coordinate in BIM world space (metres)")
    world_y: Mapped[float] = mapped_column(Float, comment="Y coordinate in BIM world space (metres)")
    world_z: Mapped[float] = mapped_column(Float, comment="Z coordinate in BIM world space (metres)")

    # Marker orientation — normal vector of the surface it's taped to
    normal_x: Mapped[float] = mapped_column(Float, default=0.0, comment="Surface normal X")
    normal_y: Mapped[float] = mapped_column(Float, default=0.0, comment="Surface normal Y")
    normal_z: Mapped[float] = mapped_column(Float, default=1.0, comment="Surface normal Z")

    # Physical size (needed for PnP — known real-world marker dimensions)
    physical_size_m: Mapped[float] = mapped_column(
        Float,
        comment="Side length of the printed marker in metres (e.g. 0.20 for 20 cm)",
    )

    # Audit
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # Relationships
    project: Mapped["Project"] = relationship(foreign_keys=[project_id])  # noqa: F821
    bim_model: Mapped["BIMModel | None"] = relationship(foreign_keys=[bim_model_id])  # noqa: F821
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])  # noqa: F821

    @property
    def world_position(self) -> dict[str, float]:
        """Return the marker's world position as a dict."""
        return {"x": self.world_x, "y": self.world_y, "z": self.world_z}

    @property
    def surface_normal(self) -> dict[str, float]:
        """Return the surface normal as a dict."""
        return {"x": self.normal_x, "y": self.normal_y, "z": self.normal_z}

    def __repr__(self) -> str:
        return (
            f"<FiducialMarker(id={self.id}, marker_dict_id={self.marker_dict_id}, "
            f"pos=({self.world_x:.2f}, {self.world_y:.2f}, {self.world_z:.2f}))>"
        )
