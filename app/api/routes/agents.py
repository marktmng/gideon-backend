"""API routes for Phase 5 AI Agents, Orchestrated Tasks, Tools, Approvals, and Daily Summaries."""
import uuid
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, status, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.api.dependencies import get_db, get_agent_service, get_daily_summary_service
from app.core.config import settings
from app.core.exceptions import EntityNotFoundError
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import (
    AgentListResponse,
    ToolListResponse,
    AgentTaskCreate,
    AgentTaskRead,
    AgentTaskListResponse,
    AgentTaskProgress,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalDecisionEnum,
    DailySummaryCreate,
    DailySummaryRead,
    DailySummaryListResponse,
    DailySummaryConfigResponse,
)
from app.services.agent_service import AgentService
from app.services.daily_summary_service import DailySummaryService

router = APIRouter(prefix="/agents", tags=["AI Agents & Automation"])


@router.get(
    "",
    response_model=AgentListResponse,
    summary="List all registered specialized agents"
)
def list_agents(service: AgentService = Depends(get_agent_service)):
    items = service.list_agents()
    return AgentListResponse(items=items, total=len(items))


@router.get(
    "/tools",
    response_model=ToolListResponse,
    summary="List all registered tools and parameter schemas"
)
def list_tools(service: AgentService = Depends(get_agent_service)):
    items = service.list_tools()
    return ToolListResponse(items=items, total=len(items))


@router.post(
    "/tasks",
    response_model=AgentTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create and initiate an orchestrated multi-step task"
)
def create_task(
    payload: AgentTaskCreate,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service)
):
    try:
        return service.create_task(db=db, payload=payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to initialize task: {str(e)}")


@router.get(
    "/tasks",
    response_model=AgentTaskListResponse,
    summary="List orchestrated tasks with optional status filter and pagination"
)
def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status (queued, running, completed, failed, etc.)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service)
):
    skip = (page - 1) * limit
    items, total = service.list_tasks(db=db, status=status, skip=skip, limit=limit)
    return AgentTaskListResponse(items=items, total=total, page=page, limit=limit)


@router.get(
    "/tasks/{task_id}",
    response_model=AgentTaskRead,
    summary="Retrieve task details, steps, execution logs, and approvals"
)
def get_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service)
):
    try:
        return service.get_task(db=db, task_id=task_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/tasks/{task_id}/progress",
    response_model=AgentTaskProgress,
    summary="Retrieve current task execution progress"
)
def get_task_progress(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service)
):
    try:
        return service.get_task_progress(db=db, task_id=task_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=AgentTaskRead,
    summary="Cancel an active task and abort remaining steps"
)
def cancel_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service)
):
    try:
        return service.cancel_task(db=db, task_id=task_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/tasks/{task_id}/approvals/{approval_id}",
    response_model=ApprovalDecisionResponse,
    summary="Submit approve or reject decision for a pending consequential action"
)
def decide_approval(
    task_id: uuid.UUID,
    approval_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service)
):
    try:
        return service.decide_approval(
            db=db,
            task_id=task_id,
            approval_id=approval_id,
            decision=payload.decision,
            reason=payload.reason,
            bound_action=payload.bound_action,
            bound_target=payload.bound_target,
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/tasks/{task_id}/approve",
    response_model=ApprovalDecisionResponse,
    summary="Shortcut: Approve active pending action for a task"
)
def approve_task_action(
    task_id: uuid.UUID,
    payload: Optional[ApprovalDecisionRequest] = None,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service)
):
    progress = service.get_task_progress(db=db, task_id=task_id)
    if not progress.pending_approval_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending approval exists for this task.")

    reason = payload.reason if payload else None
    bound_action = payload.bound_action if payload else None
    bound_target = payload.bound_target if payload else None

    return service.decide_approval(
        db=db,
        task_id=task_id,
        approval_id=progress.pending_approval_id,
        decision=ApprovalDecisionEnum.approved,
        reason=reason,
        bound_action=bound_action,
        bound_target=bound_target,
    )


@router.post(
    "/tasks/{task_id}/reject",
    response_model=ApprovalDecisionResponse,
    summary="Shortcut: Reject active pending action for a task"
)
def reject_task_action(
    task_id: uuid.UUID,
    payload: Optional[ApprovalDecisionRequest] = None,
    db: Session = Depends(get_db),
    service: AgentService = Depends(get_agent_service)
):
    progress = service.get_task_progress(db=db, task_id=task_id)
    if not progress.pending_approval_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending approval exists for this task.")

    reason = payload.reason if payload else "User rejected action."
    return service.decide_approval(
        db=db,
        task_id=task_id,
        approval_id=progress.pending_approval_id,
        decision=ApprovalDecisionEnum.rejected,
        reason=reason,
    )


@router.get(
    "/tasks/{task_id}/events",
    summary="Subscribe to Server-Sent Events (SSE) for task and step progress"
)
async def subscribe_task_events(
    task_id: uuid.UUID,
    service: AgentService = Depends(get_agent_service)
):
    return StreamingResponse(
        service.event_publisher.stream_events(task_id=str(task_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get(
    "/events",
    summary="Subscribe to global Server-Sent Events (SSE) across all agent tasks"
)
async def subscribe_global_events(
    service: AgentService = Depends(get_agent_service)
):
    return StreamingResponse(
        service.event_publisher.stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ---------------------------------------------------------------------------
# Phase 5 Addition: Daily Business Summary Routes
# ---------------------------------------------------------------------------

@router.post(
    "/summaries/generate",
    response_model=DailySummaryRead,
    summary="Generate consolidated daily business summary"
)
def generate_daily_summary(
    payload: Optional[DailySummaryCreate] = None,
    db: Session = Depends(get_db),
    summary_service: DailySummaryService = Depends(get_daily_summary_service),
):
    """Generate or retrieve the end-of-day business summary aggregating agent tasks,
    marketing outreach, customer operations, and pending approvals.
    """
    target_date = payload.summary_date if payload else None
    force = payload.force_regenerate if payload else False
    delivery = payload.delivery_channel if payload else None
    return summary_service.generate_summary(
        db=db,
        target_date=target_date,
        force_regenerate=force,
        delivery_channel=delivery,
    )


@router.get(
    "/summaries",
    response_model=DailySummaryListResponse,
    summary="List historical daily business summaries"
)
def list_daily_summaries(
    limit: int = Query(30, ge=1, le=100, description="Maximum number of historical summaries"),
    db: Session = Depends(get_db),
):
    """Retrieve historical daily summaries ordered by most recent date."""
    repo = AgentRepository(db)
    items = repo.list_daily_summaries(limit=limit)
    return DailySummaryListResponse(items=items, total=len(items))


@router.get(
    "/summaries/config",
    response_model=DailySummaryConfigResponse,
    summary="Get daily business summary scheduling and delivery configuration"
)
def get_daily_summary_config():
    """Get active schedule time, timezone, and delivery channel settings."""
    return DailySummaryConfigResponse(
        schedule_time=settings.summary_schedule_time,
        timezone=settings.summary_timezone,
        delivery_channel=settings.summary_delivery_channel,
        delivery_email=settings.summary_delivery_email,
        delivery_webhook=settings.summary_webhook_url,
        auto_schedule=settings.summary_auto_schedule,
    )


@router.get(
    "/summaries/date/{summary_date}",
    response_model=DailySummaryRead,
    summary="Get daily business summary for a specific date"
)
def get_daily_summary_by_date(
    summary_date: date,
    db: Session = Depends(get_db),
):
    """Retrieve an existing business summary for a specific calendar date (YYYY-MM-DD)."""
    repo = AgentRepository(db)
    summary = repo.get_daily_summary_by_date(summary_date)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No daily summary found for date {summary_date.isoformat()}."
        )
    return summary


@router.post(
    "/summaries/webhook",
    response_model=DailySummaryRead,
    summary="Trigger daily business summary via external webhook (e.g. n8n)"
)
def trigger_daily_summary_webhook(
    payload: Optional[DailySummaryCreate] = None,
    db: Session = Depends(get_db),
    summary_service: DailySummaryService = Depends(get_daily_summary_service),
):
    """Webhook trigger compatible with n8n or external schedulers. Forces summary generation."""
    target_date = payload.summary_date if payload else None
    delivery = payload.delivery_channel if payload else None
    return summary_service.generate_summary(
        db=db,
        target_date=target_date,
        force_regenerate=True,
        delivery_channel=delivery,
    )
