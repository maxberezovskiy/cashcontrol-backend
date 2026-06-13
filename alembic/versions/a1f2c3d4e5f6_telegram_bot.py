"""telegram bot: user.telegram_id + telegram_link_codes

Revision ID: a1f2c3d4e5f6
Revises: 74b18205dd15
Create Date: 2026-06-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f2c3d4e5f6'
down_revision: Union[str, None] = '74b18205dd15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('telegram_id', sa.BigInteger(), nullable=True))
    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'], unique=True)

    op.create_table(
        'telegram_link_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=16), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_telegram_link_codes_id'), 'telegram_link_codes', ['id'], unique=False)
    op.create_index(op.f('ix_telegram_link_codes_code'), 'telegram_link_codes', ['code'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_telegram_link_codes_code'), table_name='telegram_link_codes')
    op.drop_index(op.f('ix_telegram_link_codes_id'), table_name='telegram_link_codes')
    op.drop_table('telegram_link_codes')
    op.drop_index(op.f('ix_users_telegram_id'), table_name='users')
    op.drop_column('users', 'telegram_id')
