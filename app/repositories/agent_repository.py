"""Repository for persisting agent tasks, execution steps, approvals, logs, and daily summaries."""
import uuid
from datetime import datetime, date, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session, selectinload
from app.models.agent import AgentTask, AgentTaskStep, AgentApproval, AgentExecutionLog, DailyBusinessSummary
from app.schemas.agent import TaskStatusEnum, StepStatusEnum, AgentPlan


class AgentRepository:
    """Manages database transactions for agent tasks, steps, approvals, logs, and daily summaries."""

    def __init__(self, db: Session):
        self.db = db

    def create_task_with_plan(
        self,
        user_request: str,
        title: Optional[str],
        assigned_agent_id: Optional[str],
        plan: AgentPlan,
    ) -> AgentTask:
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        task_title = title or (f"Task: {user_request[:50]}..." if len(user_request) > 50 else user_request)

        task = AgentTask(
            id=task_id,
            title=task_title,
            user_request=user_request,
            assigned_agent_id=assigned_agent_id,
            status=TaskStatusEnum.queued.value,
            progress_percent=0,
            plan=plan.model_dump(),
            created_at=now,
        )
        self.db.add(task)

        for step in plan.steps:
            db_step = AgentTaskStep(
                id=uuid.uuid4(),
                task_id=task_id,
                step_key=step.step_key,
                step_order=step.step_order,
                description=step.description,
                assigned_agent_id=step.assigned_agent_id,
                tool_id=step.tool_id,
                input_data=step.input_data,
                dependencies=step.dependencies,
                status=StepStatusEnum.pending.value,
                requires_approval=step.requires_approval,
                max_retries=step.max_retries,
                retry_count=0,
            )
            self.db.add(db_step)

        self.db.commit()
        return self.get_task(task_id)  # type: ignore

    def get_task(self, task_id: uuid.UUID) -> Optional[AgentTask]:
        stmt = (
            select(AgentTask)
            .options(
                selectinload(AgentTask.steps),
                selectinload(AgentTask.approvals),
                selectinload(AgentTask.execution_logs)
            )
            .where(AgentTask.id == task_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_tasks(
        self,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[AgentTask], int]:
        stmt = select(AgentTask).options(
            selectinload(AgentTask.steps),
            selectinload(AgentTask.approvals)
        )
        count_stmt = select(func.count(AgentTask.id))

        if status:
            stmt = stmt.where(AgentTask.status == status)
            count_stmt = count_stmt.where(AgentTask.status == status)

        stmt = stmt.order_by(desc(AgentTask.created_at)).offset(skip).limit(limit)
        items = list(self.db.execute(stmt).scalars().all())
        total = self.db.execute(count_stmt).scalar() or 0
        return items, total

    def update_task_status(
        self,
        task_id: uuid.UUID,
        status: str,
        progress_percent: Optional[int] = None,
        result_summary: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[AgentTask]:
        task = self.get_task(task_id)
        if not task:
            return None

        now = datetime.now(timezone.utc)
        task.status = status
        if status == TaskStatusEnum.running.value and not task.started_at:
            task.started_at = now
        elif status in (TaskStatusEnum.completed.value, TaskStatusEnum.failed.value, TaskStatusEnum.cancelled.value):
            task.completed_at = now

        if progress_percent is not None:
            task.progress_percent = max(0, min(100, progress_percent))
        if result_summary is not None:
            task.result_summary = result_summary
        if error_message is not None:
            task.error_message = error_message

        self.db.commit()
        return task

    def update_step_status(
        self,
        step_id: uuid.UUID,
        status: str,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        increment_retry: bool = False,
    ) -> Optional[AgentTaskStep]:
        stmt = select(AgentTaskStep).where(AgentTaskStep.id == step_id)
        step = self.db.execute(stmt).scalar_one_or_none()
        if not step:
            return None

        now = datetime.now(timezone.utc)
        step.status = status
        if status == StepStatusEnum.running.value and not step.started_at:
            step.started_at = now
        elif status in (StepStatusEnum.completed.value, StepStatusEnum.failed.value, StepStatusEnum.skipped.value, StepStatusEnum.cancelled.value):
            step.completed_at = now

        if output_data is not None:
            step.output_data = output_data
        if error_message is not None:
            step.error_message = error_message
        if increment_retry:
            step.retry_count += 1

        self.db.commit()
        return step

    def create_approval(self, approval: AgentApproval) -> AgentApproval:
        self.db.add(approval)
        self.db.commit()
        self.db.refresh(approval)
        return approval

    def get_approval(self, approval_id: uuid.UUID) -> Optional[AgentApproval]:
        stmt = select(AgentApproval).where(AgentApproval.id == approval_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_pending_approval_for_task(self, task_id: uuid.UUID) -> Optional[AgentApproval]:
        stmt = (
            select(AgentApproval)
            .where(AgentApproval.task_id == task_id, AgentApproval.decision == "pending")
            .order_by(desc(AgentApproval.created_at))
        )
        return self.db.execute(stmt).scalars().first()

    def list_pending_approvals(self) -> List[AgentApproval]:
        stmt = (
            select(AgentApproval)
            .where(AgentApproval.decision == "pending")
            .order_by(desc(AgentApproval.created_at))
        )
        return list(self.db.execute(stmt).scalars().all())

    def add_execution_log(
        self,
        task_id: uuid.UUID,
        event_type: str,
        message: str,
        step_key: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> AgentExecutionLog:
        log = AgentExecutionLog(
            id=uuid.uuid4(),
            task_id=task_id,
            step_key=step_key,
            event_type=event_type,
            message=message,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(log)
        self.db.commit()
        return log

    # Daily Summary persistence methods
    def create_daily_summary(self, summary: DailyBusinessSummary) -> DailyBusinessSummary:
        self.db.add(summary)
        self.db.commit()
        self.db.refresh(summary)
        return summary

    def get_daily_summary_by_date(self, summary_date: date) -> Optional[DailyBusinessSummary]:
        stmt = (
            select(DailyBusinessSummary)
            .where(DailyBusinessSummary.summary_date == summary_date)
            .order_by(desc(DailyBusinessSummary.created_at))
        )
        return self.db.execute(stmt).scalars().first()

    def get_daily_summary_by_id(self, summary_id: uuid.UUID) -> Optional[DailyBusinessSummary]:
        stmt = select(DailyBusinessSummary).where(DailyBusinessSummary.id == summary_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_daily_summaries(self, limit: int = 30) -> List[DailyBusinessSummary]:
        stmt = (
            select(DailyBusinessSummary)
            .order_by(desc(DailyBusinessSummary.summary_date), desc(DailyBusinessSummary.created_at))
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_tasks_for_date_range(self, start_dt: datetime, end_dt: datetime) -> List[AgentTask]:
        stmt = (
            select(AgentTask)
            .options(
                selectinload(AgentTask.steps),
                selectinload(AgentTask.approvals),
                selectinload(AgentTask.execution_logs)
            )
            .where(AgentTask.created_at >= start_dt, AgentTask.created_at <= end_dt)
            .order_by(AgentTask.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())
