"""add voice field to channel

Revision ID: 0a8e3a073c77
Revises: 0fcb9674ca71
Create Date: 2026-05-06 18:11:50.032569

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0a8e3a073c77'
down_revision = '0fcb9674ca71'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("channel", sa.Column("voice", sa.Boolean(), nullable=False, server_default="false"))


def downgrade():
    op.drop_column("channel", "voice")
