"""add voice channel fields to game

Revision ID: 0fcb9674ca71
Revises: a1ff08bec51d
Create Date: 2026-05-06 17:12:17.680689

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0fcb9674ca71'
down_revision = 'a1ff08bec51d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("game", sa.Column("voice_channel_id", sa.String(), nullable=True))
    op.add_column("game", sa.Column("create_voice", sa.Boolean(), nullable=False, server_default="false"))


def downgrade():
    op.drop_column("game", "create_voice")
    op.drop_column("game", "voice_channel_id")
