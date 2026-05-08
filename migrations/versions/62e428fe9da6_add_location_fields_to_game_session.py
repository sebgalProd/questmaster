"""add location fields to game_session

Revision ID: 62e428fe9da6
Revises: 880e807b0afe
Create Date: 2026-05-08 16:09:40.184807

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '62e428fe9da6'
down_revision = '880e807b0afe'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE TYPE session_location_enum AS ENUM ('online', 'inperson')")
    op.add_column(
        'game_session',
        sa.Column(
            'location_type',
            sa.Enum('online', 'inperson', name='session_location_enum'),
            nullable=True,
        ),
    )
    op.add_column('game_session', sa.Column('location_label', sa.String(), nullable=True))
    op.add_column('game_session', sa.Column('location_url', sa.String(), nullable=True))


def downgrade():
    op.drop_column('game_session', 'location_url')
    op.drop_column('game_session', 'location_label')
    op.drop_column('game_session', 'location_type')
    op.execute("DROP TYPE session_location_enum")
