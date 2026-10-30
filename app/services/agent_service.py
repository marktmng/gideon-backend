"""Unified Agent Service orchestrating tasks, approvals, events, and background lifecycles."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from app.agents.registry import AgentRegistry
from app.agents.tools.registry import ToolRegistry
from app.agents.approval.manager import ApprovalManager
from app.agents.events.publisher import ProgressEventPublisher
from app.agents.orchestrator.planner import TaskPlanner
from app.agents.orchestrator.engine import TaskOrchestrator
from app.ai.base import BaseAIProvider
from app.ai.provider_factory import AIProviderFactory
from app.core.exceptions import EntityNotFoundError, AIConfigurationError
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.agent import AgentTask, AgentApproval
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import (
    AgentDefinitionRead,
    ToolDefinitionRead,
    AgentTaskRead,
    AgentTaskCreate,
    AgentTaskProgress,
    ApprovalRead,
    ApprovalDecisionEnum,
    ApprovalDecisionResponse,
    TaskStatusEnum,
    StepStatusEnum,
)

logger = get_logger(__name__)


class AgentService:
    """Service coordinating multi-step agent automation and task lifecycles."""

    def __init__(
        self,
        agent_registry: Optional[AgentRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None,
        approval_manager: Optional[ApprovalManager] = None,
        event_publisher: Optional[ProgressEventPublisher] = None,
        orchestrator: Optional[TaskOrchestrator] = None,
        ai_provider: Optional[BaseAIProvider] = None,
        desktop_service: Optional[Any] = None,
    ):
        self.agent_registry = agent_registry or AgentRegistry()
        self.tool_registry = tool_registry or ToolRegistry()
        self.approval_manager = approval_manager or ApprovalManager(self.tool_registry)
        self.event_publisher = event_publisher or ProgressEventPublisher()
        self.planner = TaskPlanner(self.agent_registry, self.tool_registry)
        self.orchestrator = orchestrator or TaskOrchestrator(
            agent_registry=self.agent_registry,
            tool_registry=self.tool_registry,
            approval_manager=self.approval_manager,
            event_publisher=self.event_publisher,
        )
        self.desktop_service = desktop_service
        self.ai_provider = ai_provider
        if self.ai_provider is None:
            try:
                self.ai_provider = AIProviderFactory.get_provider()
            except AIConfigurationError:
                self.ai_provider = None

    def list_agents(self) -> List[AgentDefinitionRead]:
        return self.agent_registry.list_agents()

    def list_tools(self) -> List[ToolDefinitionRead]:
        return self.tool_registry.list_tools()

    def create_task(
        self,
        db: Session,
        payload: AgentTaskCreate,
    ) -> AgentTaskRead:
        """Create and plan an orchestrated task, persisting the validated plan."""
        repo = AgentRepository(db)
        # Formulate and validate execution plan
        plan = self.planner.create_plan(
            user_request=payload.user_request,
            preferred_agent_id=payload.assigned_agent_id,
            context=payload.initial_context,
        )

        task = repo.create_task_with_plan(
            user_request=payload.user_request,
            title=payload.title,
            assigned_agent_id=payload.assigned_agent_id or (plan.steps[0].assigned_agent_id if plan.steps else None),
            plan=plan,
        )
        repo.add_execution_log(
            task_id=task.id,
            event_type="agent.task.created",
            message=f"Task planned with {len(plan.steps)} steps.",
            payload={"steps_count": len(plan.steps)}
        )

        # Trigger background execution asynchronously if an event loop is running
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self.orchestrator.run_task(
                    task_id=task.id,
                    db_factory=SessionLocal,
                    ai_provider=self.ai_provider,
                    desktop_service=self.desktop_service,
                )
            )
        except RuntimeError:
            pass

        return AgentTaskRead.model_validate(task)

    def get_task(self, db: Session, task_id: uuid.UUID) -> AgentTaskRead:
        repo = AgentRepository(db)
        task = repo.get_task(task_id)
        if not task:
            raise EntityNotFoundError(f"Agent task '{task_id}' was not found.")
        return AgentTaskRead.model_validate(task)

    def list_tasks(
        self,
        db: Session,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[AgentTaskRead], int]:
        repo = AgentRepository(db)
        items, total = repo.list_tasks(status=status, skip=skip, limit=limit)
        return [AgentTaskRead.model_validate(t) for t in items], total

    def get_task_progress(self, db: Session, task_id: uuid.UUID) -> AgentTaskProgress:
        repo = AgentRepository(db)
        task = repo.get_task(task_id)
        if not task:
            raise EntityNotFoundError(f"Agent task '{task_id}' was not found.")

        steps = list(task.steps)
        total_steps = len(steps)
        completed_count = sum(1 for s in steps if s.status == StepStatusEnum.completed.value)
        active_step = next((s.step_key for s in steps if s.status in (StepStatusEnum.running.value, StepStatusEnum.awaiting_approval.value)), None)
        pending_approval = repo.get_pending_approval_for_task(task_id)

        return AgentTaskProgress(
            task_id=task.id,
            status=TaskStatusEnum(task.status),
            progress_percent=task.progress_percent,
            active_step_key=active_step,
            completed_steps_count=completed_count,
            total_steps_count=total_steps,
            pending_approval_id=pending_approval.id if pending_approval else None,
            updated_at=datetime.now(timezone.utc),
        )

    def cancel_task(self, db: Session, task_id: uuid.UUID) -> AgentTaskRead:
        repo = AgentRepository(db)
        task = repo.get_task(task_id)
        if not task:
            raise EntityNotFoundError(f"Agent task '{task_id}' was not found.")

        self.orchestrator.cancel_task(task_id)
        repo.update_task_status(task_id, TaskStatusEnum.cancelled.value, error_message="Cancelled by user.")
        # Mark pending steps as cancelled
        for s in (task.steps or []):
            if s.status in (StepStatusEnum.pending.value, StepStatusEnum.running.value, StepStatusEnum.awaiting_approval.value):
                repo.update_step_status(s.id, StepStatusEnum.cancelled.value)

        # Invalidate any pending approval requests to prevent consequential actions from executing
        for a in (task.approvals or []):
            if a.decision == ApprovalDecisionEnum.pending.value:
                a.decision = ApprovalDecisionEnum.rejected.value
                a.decision_reason = "Parent task cancelled by user."
                a.decided_at = datetime.now(timezone.utc)
        db.commit()

        repo.add_execution_log(task_id, "agent.task.cancelled", "Task cancellation confirmed.")
        return AgentTaskRead.model_validate(repo.get_task(task_id))

    def decide_approval(
        self,
        db: Session,
        task_id: uuid.UUID,
        approval_id: uuid.UUID,
        decision: ApprovalDecisionEnum,
        reason: Optional[str] = None,
        bound_action: Optional[str] = None,
        bound_target: Optional[str] = None,
    ) -> ApprovalDecisionResponse:
        repo = AgentRepository(db)
        task = repo.get_task(task_id)
        if not task:
            raise EntityNotFoundError(f"Agent task '{task_id}' was not found.")

        if task.status == TaskStatusEnum.cancelled.value:
            raise ValueError(f"Cannot decide approval: Task '{task_id}' has been cancelled.")
        if task.status in (TaskStatusEnum.completed.value, TaskStatusEnum.failed.value):
            raise ValueError(f"Cannot decide approval: Task '{task_id}' is in terminal state '{task.status}'.")

        approval = repo.get_approval(approval_id)
        if not approval or approval.task_id != task_id:
            raise EntityNotFoundError(f"Approval request '{approval_id}' not found for task '{task_id}'.")

        if approval.decision != ApprovalDecisionEnum.pending.value:
            raise ValueError(f"Approval request '{approval_id}' has already been decided: {approval.decision}.")

        # Check expiration (24h TTL)
        if approval.created_at:
            created = approval.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - created).total_seconds()
            if age_seconds > 86400:
                approval.decision = ApprovalDecisionEnum.rejected.value
                approval.decision_reason = "Approval request expired (TTL 24h exceeded)."
                approval.decided_at = datetime.now(timezone.utc)
                db.commit()
                raise ValueError(f"Approval request '{approval_id}' has expired and cannot be approved.")

        # Enforce parameter binding
        updated_approval = self.approval_manager.validate_and_apply_decision(
            approval=approval,
            decision=decision,
            reason=reason,
            bound_action=bound_action,
            bound_target=bound_target,
        )
        db.commit()

        # Update step state based on human decision
        if approval.step_id:
            if decision == ApprovalDecisionEnum.approved:
                # Clear step requires_approval so it can run
                repo.update_step_status(approval.step_id, StepStatusEnum.pending.value)
                repo.update_task_status(task_id, TaskStatusEnum.running.value)
                repo.add_execution_log(
                    task_id=task_id,
                    event_type="agent.approval.granted",
                    message=f"Action '{approval.action_type}' was approved by user.",
                )
                # Resume execution loop
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        self.orchestrator.run_task(
                            task_id=task_id,
                            db_factory=SessionLocal,
                            ai_provider=self.ai_provider,
                            desktop_service=self.desktop_service,
                        )
                    )
                except RuntimeError:
                    pass
            else:
                # Rejected
                repo.update_step_status(
                    approval.step_id,
                    StepStatusEnum.failed.value,
                    error_message=f"Action '{approval.action_type}' was rejected by user. {reason or ''}".strip()
                )
                repo.update_task_status(task_id, TaskStatusEnum.failed.value, error_message="Task stopped due to rejected consequential action.")
                repo.add_execution_log(
                    task_id=task_id,
                    event_type="agent.approval.rejected",
                    message=f"Action '{approval.action_type}' was rejected by user.",
                )

        updated_task = repo.get_task(task_id)
        return ApprovalDecisionResponse(
            approval=ApprovalRead.model_validate(updated_approval),
            task_status=TaskStatusEnum(updated_task.status),
            message=f"Approval decision '{decision.value}' recorded.",
        )
