"""Marker orientation and BIM model identity for mapped defects."""
from alembic import op
import sqlalchemy as sa

revision = "20261118_hardening"
down_revision = "ebd783f16a47"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cameras", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cameras", sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table("audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_audit_events_project_id", "audit_events", ["project_id"])
    op.add_column("fiducial_markers", sa.Column("rotation_deg", sa.Float(), server_default="0", nullable=False))
    op.add_column("defects", sa.Column("bim_model_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_defects_bim_model", "defects", "bim_models", ["bim_model_id"], ["id"])
    op.create_index("ix_defects_project_model", "defects", ["project_id", "bim_model_id"])
    op.alter_column("cameras", "calibration_status", server_default="uncalibrated")


def downgrade():
    op.drop_column("cameras", "claimed_until")
    op.drop_column("cameras", "last_attempt_at")
    op.drop_table("audit_events")
    op.drop_index("ix_defects_project_model", table_name="defects")
    op.drop_constraint("fk_defects_bim_model", "defects", type_="foreignkey")
    op.drop_column("defects", "bim_model_id")
    op.drop_column("fiducial_markers", "rotation_deg")
