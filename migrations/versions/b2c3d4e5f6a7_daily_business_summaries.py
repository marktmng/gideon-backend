"""daily_business_summaries

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-29 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'daily_business_summaries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('summary_date', sa.Date(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('marketing_activity', sa.JSON(), nullable=True),
        sa.Column('customer_operations', sa.JSON(), nullable=True),
        sa.Column('task_metrics', sa.JSON(), nullable=False),
        sa.Column('pending_approvals', sa.JSON(), nullable=True),
        sa.Column('recommended_priorities', sa.JSON(), nullable=True),
        sa.Column('raw_content', sa.Text(), nullable=False),
        sa.Column('delivery_channel', sa.String(length=32), nullable=False, server_default='local'),
        sa.Column('delivery_status', sa.String(length=32), nullable=False, server_default='stored_locally'),
        sa.Column('delivery_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('daily_business_summaries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_daily_business_summaries_summary_date'), ['summary_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_daily_business_summaries_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('daily_business_summaries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_daily_business_summaries_created_at'))
        batch_op.drop_index(batch_op.f('ix_daily_business_summaries_summary_date'))
    op.drop_table('daily_business_summaries')

