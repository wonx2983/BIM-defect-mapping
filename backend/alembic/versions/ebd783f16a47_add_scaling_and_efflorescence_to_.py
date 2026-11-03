"""add_scaling_and_efflorescence_to_defectclass

Revision ID: ebd783f16a47
Revises: 513e82a138f3
Create Date: 2026-11-03 15:49:43.914223

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ebd783f16a47'
down_revision: Union[str, None] = '513e82a138f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE defectclass ADD VALUE IF NOT EXISTS 'EFFLORESCENCE'")
    op.execute("ALTER TYPE defectclass ADD VALUE IF NOT EXISTS 'SCALING'")


def downgrade() -> None:
    pass
