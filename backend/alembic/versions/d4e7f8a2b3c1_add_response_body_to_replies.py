"""add_response_body_to_replies

Revision ID: d4e7f8a2b3c1
Revises: 2f516ea3e0b8
Create Date: 2026-05-05 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e7f8a2b3c1'
down_revision: Union[str, None] = '2f516ea3e0b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('replies', sa.Column('response_body', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('replies', 'response_body')
