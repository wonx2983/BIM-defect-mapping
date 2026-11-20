"""Enforce one physical location per printed marker within each project."""
from alembic import op
import sqlalchemy as sa

revision = "20261120_marker_identity"
down_revision = "20261118_hardening"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("monitoring_workers",
                    sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False))
    op.create_unique_constraint("uq_project_marker_pattern", "fiducial_markers",
                               ["project_id", "aruco_dict_type", "marker_dict_id"])


def downgrade():
    op.drop_table("monitoring_workers")
    op.drop_constraint("uq_project_marker_pattern", "fiducial_markers", type_="unique")
