"""add_signal_tables

Adds lead_signals and signal_cache tables for the signal-centric enrichment pipeline (v2).
Also adds signal_breakdown, pipeline_version, and scored_at to lead_scores.
All changes are additive – existing data and the v1 pipeline are unaffected.

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-17 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── lead_signals ──────────────────────────────────────────────────────────
    op.create_table(
        'lead_signals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('lead_id', sa.UUID(), nullable=False),
        sa.Column('signal_type', sa.String(50), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('provider', sa.String(100), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('cached_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lead_signals_lead_id', 'lead_signals', ['lead_id'])
    op.create_index('ix_lead_signals_signal_type', 'lead_signals', ['signal_type'])
    op.create_index('ix_lead_signals_tenant_id', 'lead_signals', ['tenant_id'])

    # ── signal_cache ──────────────────────────────────────────────────────────
    op.create_table(
        'signal_cache',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('cache_key', sa.String(500), nullable=False),
        sa.Column('signal_type', sa.String(50), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('provider', sa.String(100), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_signal_cache_cache_key', 'signal_cache', ['cache_key'], unique=True)
    op.create_index('ix_signal_cache_expires_at', 'signal_cache', ['expires_at'])

    # ── lead_scores: new columns ───────────────────────────────────────────────
    op.add_column('lead_scores', sa.Column(
        'signal_breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
    ))
    op.add_column('lead_scores', sa.Column(
        'pipeline_version', sa.String(10), server_default='v1', nullable=False,
    ))
    op.add_column('lead_scores', sa.Column(
        'scored_at', sa.DateTime(timezone=True), nullable=True,
    ))


def downgrade() -> None:
    op.drop_column('lead_scores', 'scored_at')
    op.drop_column('lead_scores', 'pipeline_version')
    op.drop_column('lead_scores', 'signal_breakdown')
    op.drop_index('ix_signal_cache_expires_at', table_name='signal_cache')
    op.drop_index('ix_signal_cache_cache_key', table_name='signal_cache')
    op.drop_table('signal_cache')
    op.drop_index('ix_lead_signals_tenant_id', table_name='lead_signals')
    op.drop_index('ix_lead_signals_signal_type', table_name='lead_signals')
    op.drop_index('ix_lead_signals_lead_id', table_name='lead_signals')
    op.drop_table('lead_signals')
