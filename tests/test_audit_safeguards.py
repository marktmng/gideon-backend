"""Focused audit safeguard verification tests for Gideon Phase 5 Agent Engine.

Verifies:
1. Cancellation stops pending approvals and blocks subsequent decisions.
2. Replayed, duplicated, and expired approval requests are rejected.
3. Unconfigured external integrations (web search, SMTP) report honest statuses without simulations.
4. Server restart reconciliation handles orphaned running/planning tasks.
"""
import uuid
import os
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.orm import Session

from app.models.agent import AgentTask, AgentTaskStep, AgentApproval
from app.schemas.agent import (
    TaskStatusEnum,
    StepStatusEnum,
    ApprovalDecisionEnum,
    AgentTaskCreate,
)
from app.services.agent_service import AgentService
from app.repositories.agent_repository import AgentRepository
from app.agents.tools.builtins import ResearchFetchTool, SendEmailTool
from app.main import reconcile_orphaned_agent_tasks


def test_cancel_task_rejects_pending_approvals_and_prevents_execution(db_session: Session):
    """Test that cancelling a task immediately invalidates pending approvals and blocks further approval."""
    service = AgentService()
    task = service.create_task(
        db=db_session,
        payload=AgentTaskCreate(
            title="Outreach Task",
            user_request="Send intro email to partner@example.com",
            assigned_agent_id="agent_email"
        )
    )

    # Find the consequential step requiring approval
    email_step = next(s for s in task.steps if s.tool_id == "tool_send_email")

    # Create pending approval
    approval = service.approval_manager.create_approval_request(
        task_id=task.id,
        step_id=email_step.id,
        agent_id="agent_email",
        action_type="Send Email Message",
        description="Send email to partner@example.com",
        target_resource="tool_send_email",
        parameters={"recipient": "partner@example.com"},
    )
    from app.repositories.agent_repository import AgentRepository
    repo = AgentRepository(db_session)
    repo.create_approval(approval)
    repo.update_task_status(task.id, TaskStatusEnum.awaiting_approval.value)
    repo.update_step_status(email_step.id, StepStatusEnum.awaiting_approval.value)

    # Cancel the task
    cancelled_task = service.cancel_task(db=db_session, task_id=task.id)
    assert cancelled_task.status == TaskStatusEnum.cancelled

    # Verify step was marked cancelled
    updated_step = next(s for s in cancelled_task.steps if s.id == email_step.id)
    assert updated_step.status == StepStatusEnum.cancelled

    # Verify pending approval was marked rejected
    refreshed_approval = repo.get_approval(approval.id)
    assert refreshed_approval.decision == "rejected"
    assert "Parent task cancelled" in refreshed_approval.decision_reason

    # Attempting to approve the action on cancelled task must fail
    with pytest.raises(ValueError, match="has been cancelled|already been decided"):
        service.decide_approval(
            db=db_session,
            task_id=task.id,
            approval_id=approval.id,
            decision=ApprovalDecisionEnum.approved
        )


def test_replayed_and_expired_approvals_rejected(db_session: Session):
    """Test rejection of replayed decisions and expired approvals (>24h)."""
    service = AgentService()
    task = service.create_task(
        db=db_session,
        payload=AgentTaskCreate(
            title="Review Task",
            user_request="Send follow up email to client@example.com",
            assigned_agent_id="agent_email"
        )
    )
    repo = AgentRepository(db_session)
    repo.update_task_status(task.id, TaskStatusEnum.awaiting_approval.value)

    # 1. Test replayed approval
    approval = service.approval_manager.create_approval_request(
        task_id=task.id,
        step_id=None,
        agent_id="agent_email",
        action_type="Send Email Message",
        description="Send test email",
        target_resource="tool_send_email",
    )
    repo.create_approval(approval)

    # First decision succeeds
    resp1 = service.decide_approval(
        db=db_session,
        task_id=task.id,
        approval_id=approval.id,
        decision=ApprovalDecisionEnum.rejected,
        reason="User decided against sending"
    )
    assert resp1.approval.decision == ApprovalDecisionEnum.rejected

    # Replay attempt fails
    with pytest.raises(ValueError, match="already been decided"):
        service.decide_approval(
            db=db_session,
            task_id=task.id,
            approval_id=approval.id,
            decision=ApprovalDecisionEnum.approved
        )

    # 2. Test expired approval (>24h)
    old_time = datetime.now(timezone.utc) - timedelta(hours=25)
    expired_approval = AgentApproval(
        id=uuid.uuid4(),
        task_id=task.id,
        action_type="Send Email Message",
        agent_id="agent_email",
        description="Expired approval",
        target_resource="tool_send_email",
        decision=ApprovalDecisionEnum.pending.value,
        created_at=old_time,
    )
    repo.create_approval(expired_approval)

    with pytest.raises(ValueError, match="has expired"):
        service.decide_approval(
            db=db_session,
            task_id=task.id,
            approval_id=expired_approval.id,
            decision=ApprovalDecisionEnum.approved
        )


@pytest.mark.asyncio
async def test_honest_integration_statuses_when_unconfigured():
    """Verify research and email tools report honest unconfigured status without false success claims."""
    # Ensure unconfigured environment
    old_search = os.environ.pop("EXTERNAL_SEARCH_API_KEY", None)
    old_smtp = os.environ.pop("SMTP_HOST", None)

    try:
        # 1. Research tool: Must explicitly report external web is unavailable
        research_tool = ResearchFetchTool()
        res_output = await research_tool.execute({"query": "Market competitors in SaaS"})
        assert res_output["external_web_available"] is False
        assert "Live external research is unavailable" in res_output["capability_notice"]
        assert "external_web" not in res_output["sources_consulted"]

        # 2. Email tool: Must report unconfigured status, NOT sent, NOT simulated success
        email_tool = SendEmailTool()
        email_output = await email_tool.execute({
            "recipient": "client@example.com",
            "subject": "Greetings",
            "body": "Hello World"
        })
        assert email_output["status"] == "unconfigured"
        assert email_output["external_dispatch"] is False
        assert email_output["email_sent"] is False
        assert "SMTP is unconfigured" in email_output["message"]
        assert "simulated_success" not in email_output.get("status", "")

    finally:
        if old_search:
            os.environ["EXTERNAL_SEARCH_API_KEY"] = old_search
        if old_smtp:
            os.environ["SMTP_HOST"] = old_smtp


def test_server_restart_reconciliation(db_session: Session):
    """Test that restarting the backend reconciles orphaned running/planning tasks to failed."""
    # Create a task left in 'running' state
    now_utc = datetime.now(timezone.utc)
    orphaned_task = AgentTask(
        id=uuid.uuid4(),
        title="Interrupted Task",
        user_request="Process large data batch",
        status=TaskStatusEnum.running.value,
        progress_percent=50,
        created_at=now_utc,
        started_at=now_utc,
    )
    orphaned_step = AgentTaskStep(
        id=uuid.uuid4(),
        task_id=orphaned_task.id,
        step_key="step_1",
        step_order=1,
        description="In-flight batch step",
        assigned_agent_id="agent_business_ops",
        status=StepStatusEnum.running.value,
        started_at=now_utc,
    )
    db_session.add(orphaned_task)
    db_session.add(orphaned_step)
    db_session.commit()

    # Run the startup reconciliation function
    reconcile_orphaned_agent_tasks(db=db_session)

    # Verify task was marked failed with restart error
    repo = AgentRepository(db_session)
    task_after = repo.get_task(orphaned_task.id)
    assert task_after.status == TaskStatusEnum.failed.value
    assert "interrupted by backend server restart" in task_after.error_message.lower()

    step_after = next(s for s in task_after.steps if s.id == orphaned_step.id)
    assert step_after.status == StepStatusEnum.failed.value
    assert "interrupted by backend server restart" in step_after.error_message.lower()
