"""add game guests and organizers

Revision ID: e7a3c9d1f2b6
Revises: c5f2d8e1b3a4
Create Date: 2026-11-11 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7a3c9d1f2b6'
down_revision = 'c5f2d8e1b3a4'
branch_labels = None
depends_on = None


def upgrade():
    for table in ("game_guests", "game_organizers"):
        op.create_table(
            table,
            sa.Column(
                "game_id",
                sa.BigInteger(),
                sa.ForeignKey("game.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("user.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )


def downgrade():
    op.drop_table("game_organizers")
    op.drop_table("game_guests")
