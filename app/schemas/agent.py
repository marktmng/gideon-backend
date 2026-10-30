"""Pydantic schemas for the Phase 5 Agent Engine, Tools, Orchestrator, Approvals, and Daily Summaries."""
from datetime import datetime, date
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid
from pydantic import BaseModel, Field, ConfigDict


class AgentStatusEnum(str, Enum):
    ready = "ready"
    disabled = "disabled"
    busy = "busy"


class TaskStatusEnum(str, Enum):
    queued = "queued"
    planning = "planning"
    running = "running"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class StepStatusEnum(str, Enum):
    pending = "pending"
    running = "running"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"
    cancelled = "cancelled"


class ToolPermissionLevel(str, Enum):
    read_only = "read_only"
    local_changes = "local_changes"
    consequential = "consequential"


class ApprovalDecisionEnum(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# Tool schemas
class ToolDefinitionRead(BaseModel):
    tool_id: str
    name: str
    description: str
    permission_level: ToolPermissionLevel
    requires_approval: bool
    supports_concurrency: bool
    timeout_seconds: int = 30
    parameter_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)


class ToolListResponse(BaseModel):
    items: List[ToolDefinitionRead]
    total: int


# Agent schemas
class AgentDefinitionRead(BaseModel):
    agent_id: str
    display_name: str
    description: str
    responsibility: str
    supported_task_types: List[str]
    allowed_tools: List[str]
    permission_requirements: List[str]
    timeout_seconds: int = 120
    max_retries: int = 2
    status: AgentStatusEnum = AgentStatusEnum.ready
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_format: Dict[str, Any] = Field(default_factory=dict)


class AgentListResponse(BaseModel):
    items: List[AgentDefinitionRead]
    total: int


# Step & Plan schemas
class AgentStepBase(BaseModel):
    step_key: str
    step_order: int
    description: str
    assigned_agent_id: str
    tool_id: Optional[str] = None
    input_data: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    requires_approval: bool = False
    max_retries: int = 2


class AgentStepCreate(AgentStepBase):
    pass


class AgentStepRead(AgentStepBase):
    id: uuid.UUID
    task_id: uuid.UUID
    status: StepStatusEnum
    retry_count: int = 0
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AgentPlan(BaseModel):
    goal: str
    steps: List[AgentStepCreate]


# Approval schemas
class ApprovalRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    step_id: Optional[uuid.UUID] = None
    action_type: str
    agent_id: str
    description: str
    target_resource: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    consequences_summary: Optional[str] = None
    decision: ApprovalDecisionEnum
    decision_reason: Optional[str] = None
    created_at: datetime
    decided_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecisionEnum
    reason: Optional[str] = None
    bound_action: Optional[str] = None
    bound_target: Optional[str] = None


class ApprovalDecisionResponse(BaseModel):
    approval: ApprovalRead
    task_status: TaskStatusEnum
    message: str


# Task schemas
class AgentTaskCreate(BaseModel):
    title: Optional[str] = None
    user_request: str = Field(..., min_length=1, max_length=4000)
    assigned_agent_id: Optional[str] = None
    initial_context: Optional[Dict[str, Any]] = None


class AgentTaskRead(BaseModel):
    id: uuid.UUID
    title: str
    user_request: str
    assigned_agent_id: Optional[str] = None
    status: TaskStatusEnum
    progress_percent: int = 0
    plan: Optional[Dict[str, Any]] = None
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    steps: List[AgentStepRead] = Field(default_factory=list)
    approvals: List[ApprovalRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AgentTaskListResponse(BaseModel):
    items: List[AgentTaskRead]
    total: int
    page: int
    limit: int


class AgentTaskProgress(BaseModel):
    task_id: uuid.UUID
    status: TaskStatusEnum
    progress_percent: int
    active_step_key: Optional[str] = None
    completed_steps_count: int = 0
    total_steps_count: int = 0
    pending_approval_id: Optional[uuid.UUID] = None
    updated_at: datetime


class AgentExecutionLogRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    step_key: Optional[str] = None
    event_type: str
    message: str
    payload: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Daily Business Summary Schemas
class DailySummaryCreate(BaseModel):
    summary_date: Optional[date] = None
    force_regenerate: bool = False
    delivery_channel: Optional[str] = None


class DailySummaryRead(BaseModel):
    id: uuid.UUID
    summary_date: date
    title: str
    marketing_activity: Optional[Dict[str, Any]] = None
    customer_operations: Optional[Dict[str, Any]] = None
    task_metrics: Dict[str, Any]
    pending_approvals: Optional[List[Dict[str, Any]]] = None
    recommended_priorities: Optional[List[str]] = None
    raw_content: str
    delivery_channel: str
    delivery_status: str
    delivery_error: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DailySummaryListResponse(BaseModel):
    items: List[DailySummaryRead]
    total: int


class DailySummaryConfigResponse(BaseModel):
    schedule_time: str
    timezone: str
    delivery_channel: str
    delivery_email: Optional[str] = None
    delivery_webhook: Optional[str] = None
    auto_schedule: bool = True
