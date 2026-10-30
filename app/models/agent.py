"""Agent database models for multi-step task orchestration and automation."""
import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, Date, Uuid, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, utc_now


class AgentTask(Base):
    """An orchestrated multi-step task with lifecycle tracking and plan state."""
    __tablename__ = "agent_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    user_request: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    assigned_agent_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="queued",
        nullable=False,
        index=True
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    plan: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True
    )
    result_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Relationships
    steps: Mapped[List["AgentTaskStep"]] = relationship(
        "AgentTaskStep",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="AgentTaskStep.step_order"
    )
    approvals: Mapped[List["AgentApproval"]] = relationship(
        "AgentApproval",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="AgentApproval.created_at"
    )
    execution_logs: Mapped[List["AgentExecutionLog"]] = relationship(
        "AgentExecutionLog",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="AgentExecutionLog.created_at"
    )

    def __repr__(self) -> str:
        return f"<AgentTask id={self.id} title={self.title} status={self.status} progress={self.progress_percent}%>"


class AgentTaskStep(Base):
    """An individual execution step within an orchestrated plan."""
    __tablename__ = "agent_task_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("agent_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    step_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True
    )
    step_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    assigned_agent_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )
    tool_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True
    )
    input_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True
    )
    dependencies: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
        index=True
    )
    requires_approval: Mapped[bool] = mapped_column(
        nullable=False,
        default=False
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=2,
        nullable=False
    )
    output_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    task: Mapped["AgentTask"] = relationship(
        "AgentTask",
        back_populates="steps"
    )

    def __repr__(self) -> str:
        return f"<AgentTaskStep id={self.id} key={self.step_key} status={self.status} agent={self.assigned_agent_id}>"


class AgentApproval(Base):
    """An explicit human approval request for a consequential action."""
    __tablename__ = "agent_approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("agent_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    step_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
        index=True
    )
    action_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )
    agent_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    target_resource: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    parameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True
    )
    consequences_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    decision: Mapped[str] = mapped_column(
        String(32),
        default="pending",  # pending, approved, rejected
        nullable=False,
        index=True
    )
    decision_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    task: Mapped["AgentTask"] = relationship(
        "AgentTask",
        back_populates="approvals"
    )

    def __repr__(self) -> str:
        return f"<AgentApproval id={self.id} action={self.action_type} decision={self.decision}>"


class AgentExecutionLog(Base):
    """Execution audit and progress event log for an agent task."""
    __tablename__ = "agent_execution_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("agent_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    step_key: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True
    )

    task: Mapped["AgentTask"] = relationship(
        "AgentTask",
        back_populates="execution_logs"
    )

    def __repr__(self) -> str:
        return f"<AgentExecutionLog id={self.id} event={self.event_type}>"


class DailyBusinessSummary(Base):
    """Consolidated end-of-day business summary persisted across agent operations."""
    __tablename__ = "daily_business_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4
    )
    summary_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    marketing_activity: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True
    )
    customer_operations: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True
    )
    task_metrics: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False
    )
    pending_approvals: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True
    )
    recommended_priorities: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True
    )
    raw_content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    delivery_channel: Mapped[str] = mapped_column(
        String(32),
        default="local",
        nullable=False
    )
    delivery_status: Mapped[str] = mapped_column(
        String(32),
        default="stored_locally",
        nullable=False
    )
    delivery_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True
    )

    def __repr__(self) -> str:
        return f"<DailyBusinessSummary id={self.id} date={self.summary_date} status={self.delivery_status}>"


