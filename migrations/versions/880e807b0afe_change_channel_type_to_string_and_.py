"""change channel type to string and remove voice boolean

Revision ID: 880e807b0afe
Revises: 0a8e3a073c77
Create Date: 2026-05-06 18:25:14.451761

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '880e807b0afe'
down_revision = '0a8e3a073c77'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("channel", "voice")
    op.alter_column("channel", "type", type_=sa.String(), postgresql_using="type::text")


def downgrade():
    pass
