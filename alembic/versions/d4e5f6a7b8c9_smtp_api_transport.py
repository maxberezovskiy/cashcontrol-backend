"""smtp api transport columns

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'smtp_settings',
        sa.Column('transport', sa.String(length=16), nullable=False, server_default='smtp'),
    )
    op.add_column('smtp_settings', sa.Column('api_provider', sa.String(length=32), nullable=True))
    op.add_column(
        'smtp_settings', sa.Column('api_key_encrypted', sa.String(length=1024), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('smtp_settings', 'api_key_encrypted')
    op.drop_column('smtp_settings', 'api_provider')
    op.drop_column('smtp_settings', 'transport')
