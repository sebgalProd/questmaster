"""add steam_id to user

Revision ID: c5f2d8e1b3a4
Revises: b4e1c7d2a9f3
Create Date: 2026-10-02 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5f2d8e1b3a4'
down_revision = 'b4e1c7d2a9f3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("steam_id", sa.String(), nullable=True))


def downgrade():
    op.drop_column("user", "steam_id")
