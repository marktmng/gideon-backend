"""phase5_agent_orchestration

Revision ID: a1b2c3d4e5f6
Revises: 9bb350303e1a
Create Date: 2026-10-29 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '9bb350303e1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. agent_tasks
    op.create_table(
        'agent_tasks',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('user_request', sa.Text(), nullable=False),
        sa.Column('assigned_agent_id', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('plan', sa.JSON(), nullable=True),
        sa.Column('result_summary', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('agent_tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_tasks_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_tasks_assigned_agent_id'), ['assigned_agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_tasks_created_at'), ['created_at'], unique=False)

    # 2. agent_task_steps
    op.create_table(
        'agent_task_steps',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('task_id', sa.Uuid(), nullable=False),
        sa.Column('step_key', sa.String(length=64), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('assigned_agent_id', sa.String(length=64), nullable=False),
        sa.Column('tool_id', sa.String(length=64), nullable=True),
        sa.Column('input_data', sa.JSON(), nullable=True),
        sa.Column('dependencies', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('requires_approval', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('output_data', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['agent_tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('agent_task_steps', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_task_steps_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_task_steps_step_key'), ['step_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_task_steps_status'), ['status'], unique=False)

    # 3. agent_approvals
    op.create_table(
        'agent_approvals',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('task_id', sa.Uuid(), nullable=False),
        sa.Column('step_id', sa.Uuid(), nullable=True),
        sa.Column('action_type', sa.String(length=64), nullable=False),
        sa.Column('agent_id', sa.String(length=64), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('target_resource', sa.String(length=255), nullable=True),
        sa.Column('parameters', sa.JSON(), nullable=True),
        sa.Column('consequences_summary', sa.Text(), nullable=True),
        sa.Column('decision', sa.String(length=32), nullable=False),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['agent_tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('agent_approvals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_approvals_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_approvals_step_id'), ['step_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_approvals_decision'), ['decision'], unique=False)

    # 4. agent_execution_logs
    op.create_table(
        'agent_execution_logs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('task_id', sa.Uuid(), nullable=False),
        sa.Column('step_key', sa.String(length=64), nullable=True),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['agent_tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('agent_execution_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_execution_logs_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_execution_logs_event_type'), ['event_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_execution_logs_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('agent_execution_logs')
    op.drop_table('agent_approvals')
    op.drop_table('agent_task_steps')
    op.drop_table('agent_tasks')

