"""add videogame to game_type_enum

Revision ID: a1ff08bec51d
Revises: c3d4e5f6a7b8
Create Date: 2026-05-06 10:35:30.546196

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1ff08bec51d'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE game_type_enum ADD VALUE 'videogame'")


def downgrade():
    pass
