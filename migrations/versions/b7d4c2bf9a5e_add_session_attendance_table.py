"""add session_attendance table

Revision ID: b7d4c2bf9a5e
Revises: 62e428fe9da6
Create Date: 2026-05-08 16:20:06.676888

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b7d4c2bf9a5e'
down_revision = '62e428fe9da6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'session_attendance',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('session_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('is_present', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['game_session.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'user_id', name='uix_session_user_attendance'),
    )


def downgrade():
    op.drop_table('session_attendance')
