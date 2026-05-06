"""add_imap_fields_to_sender_accounts

Revision ID: f1a2b3c4d5e6
Revises: d4e7f8a2b3c1
Create Date: 2026-05-06 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'd4e7f8a2b3c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sender_accounts', sa.Column('imap_host', sa.String(255), nullable=True))
    op.add_column('sender_accounts', sa.Column('imap_user', sa.String(255), nullable=True))
    op.add_column('sender_accounts', sa.Column('imap_password', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('sender_accounts', 'imap_password')
    op.drop_column('sender_accounts', 'imap_user')
    op.drop_column('sender_accounts', 'imap_host')
