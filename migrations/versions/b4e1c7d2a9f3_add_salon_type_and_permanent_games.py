"""add salon type and permanent games

Revision ID: b4e1c7d2a9f3
Revises: 880e807b0afe
Create Date: 2026-10-02 14:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4e1c7d2a9f3'
down_revision = '880e807b0afe'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'salon'")
    op.add_column(
        "game",
        sa.Column("permanent", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Permanent games and salons have no date, no session length, salons have no system
    op.alter_column("game", "date", existing_type=sa.DateTime(), nullable=True)
    op.alter_column("game", "session_length", existing_type=sa.DECIMAL(2, 1), nullable=True)
    op.alter_column("game", "system_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    op.alter_column("game", "system_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("game", "session_length", existing_type=sa.DECIMAL(2, 1), nullable=False)
    op.alter_column("game", "date", existing_type=sa.DateTime(), nullable=False)
    op.drop_column("game", "permanent")
