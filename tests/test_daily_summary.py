"""Tests for Scheduled Daily Business Summary service, API routes, and data aggregation."""
import uuid
from datetime import datetime, date, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.agent import AgentTask, AgentTaskStep, AgentApproval, DailyBusinessSummary
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import TaskStatusEnum, StepStatusEnum, ApprovalDecisionEnum
from app.services.daily_summary_service import DailySummaryService
from app.core.config import Settings


def test_empty_day_summary_graceful(db_session: Session):
    """Test that a day with zero agent activity produces a clean, honest summary without hallucinations."""
    test_date = date(2026, 1, 15)
    service = DailySummaryService()
    summary = service.generate_summary(db=db_session, target_date=test_date, force_regenerate=True)

    assert summary.summary_date == test_date
    assert summary.task_metrics["total_tasks"] == 0
    assert summary.task_metrics["completed_tasks"] == 0
    assert summary.task_metrics["failed_tasks"] == 0
    assert summary.task_metrics["success_rate_percent"] == 100.0

    # Ensure no fabricated leads or outreach
    assert summary.marketing_activity["leads_researched"] == []
    assert summary.marketing_activity["drafts_prepared"] == []
    assert summary.marketing_activity["outreach_sent"] == []
    assert summary.customer_operations["enquiries"] == []
    assert summary.customer_operations["unresolved_issues"] == []

    # Verify markdown report contains honest statements
    assert "No marketing activities, research, or email outreach recorded" in summary.raw_content
    assert "No customer enquiries, logged calls, or unresolved operational issues recorded" in summary.raw_content
    assert summary.delivery_status == "stored_locally"
    assert summary.delivery_error is None


def test_marketing_distinguishes_drafts_from_sent_outreach(db_session: Session):
    """Test that drafts and unapproved/failed emails are NOT counted as sent outreach."""
    test_date = date(2026, 2, 20)
    now_utc = datetime(2026, 2, 20, 14, 0, 0, tzinfo=timezone.utc)

    # Create task with a lead research step, a draft step, an unsent email step, and a verified sent step
    task = AgentTask(
        id=uuid.uuid4(),
        title="Q1 Outreach Campaign",
        user_request="Research enterprise leads, prepare drafts, and send approved messages",
        assigned_agent_id="agent_marketing",
        status=TaskStatusEnum.completed.value,
        progress_percent=100,
        result_summary="Completed outreach phase 1",
        created_at=now_utc,
    )
    db_session.add(task)

    step1 = AgentTaskStep(
        id=uuid.uuid4(),
        task_id=task.id,
        step_key="step_1",
        step_order=1,
        description="Research SaaS CTO leads in North America",
        assigned_agent_id="agent_marketing",
        status=StepStatusEnum.completed.value,
        output_data={"findings": "Identified 5 qualified enterprise prospects"},
        completed_at=now_utc,
    )
    step2 = AgentTaskStep(
        id=uuid.uuid4(),
        task_id=task.id,
        step_key="step_2",
        step_order=2,
        description="Draft introductory email to Prospect A",
        assigned_agent_id="agent_marketing",
        tool_id="tool_draft_email",
        status=StepStatusEnum.completed.value,
        input_data={"to": "prospect.a@example.com"},
        output_data={"draft_subject": "AI Operations Partnership", "draft_body": "Hello Prospect A..."},
        requires_approval=True,
        completed_at=now_utc,
    )
    step3 = AgentTaskStep(
        id=uuid.uuid4(),
        task_id=task.id,
        step_key="step_3",
        step_order=3,
        description="Draft email to Prospect B awaiting approval",
        assigned_agent_id="agent_marketing",
        tool_id="tool_send_email",
        status=StepStatusEnum.pending.value,  # NOT SENT
        input_data={"to": "prospect.b@example.com"},
        requires_approval=True,
    )
    step4 = AgentTaskStep(
        id=uuid.uuid4(),
        task_id=task.id,
        step_key="step_4",
        step_order=4,
        description="Dispatch approved confirmation email to Client C",
        assigned_agent_id="agent_marketing",
        tool_id="tool_send_email",
        status=StepStatusEnum.completed.value,  # VERIFIED SENT
        input_data={"to": "client.c@example.com", "subject": "Onboarding Complete"},
        output_data={"status": "sent", "email_sent": True, "external_dispatch": True},
        completed_at=now_utc,
    )
    db_session.add_all([step1, step2, step3, step4])
    db_session.commit()

    service = DailySummaryService()
    summary = service.generate_summary(db=db_session, target_date=test_date, force_regenerate=True)

    # Assertions
    mkt = summary.marketing_activity
    assert len(mkt["leads_researched"]) == 1
    assert "SaaS CTO leads" in mkt["leads_researched"][0]["description"]

    assert len(mkt["drafts_prepared"]) == 1
    assert mkt["drafts_prepared"][0]["recipient"] == "prospect.a@example.com"
    assert mkt["drafts_prepared"][0]["requires_approval"] is True

    # Crucial: Only step4 should be in outreach_sent. step3 (pending) must NOT be counted!
    assert len(mkt["outreach_sent"]) == 1
    assert mkt["outreach_sent"][0]["recipient"] == "client.c@example.com"
    assert mkt["outreach_sent"][0]["status"] == "sent"

    assert "Approved Outreach Dispatched (1)" in summary.raw_content
    assert "client.c@example.com" in summary.raw_content
    assert "Drafts Prepared for Review (1)" in summary.raw_content


def test_customer_operations_and_failure_priorities(db_session: Session):
    """Test customer enquiry detection, failure tracking, and next-day priority derivation."""
    test_date = date(2026, 3, 10)
    now_utc = datetime(2026, 3, 10, 11, 0, 0, tzinfo=timezone.utc)

    # 1. Customer enquiry task
    task_cust = AgentTask(
        id=uuid.uuid4(),
        title="Customer Support Enquiry - Invoice discrepancy",
        user_request="Client Acme Corp called regarding invoice #1042 discrepancy",
        assigned_agent_id="agent_business_ops",
        status=TaskStatusEnum.completed.value,
        progress_percent=100,
        result_summary="Identified billing adjustment needed for Acme Corp",
        created_at=now_utc,
    )
    # 2. Failed task
    task_fail = AgentTask(
        id=uuid.uuid4(),
        title="Sync CRM Database",
        user_request="Synchronize contacts with CRM API",
        assigned_agent_id="agent_coding",
        status=TaskStatusEnum.failed.value,
        progress_percent=40,
        error_message="Authentication failed: CRM API key expired",
        created_at=now_utc,
    )
    # 3. Pending approval
    approval = AgentApproval(
        id=uuid.uuid4(),
        task_id=task_cust.id,
        action_type="credit_note_issue",
        agent_id="agent_business_ops",
        description="Issue $500 credit note to Acme Corp",
        target_resource="Finance/AcmeCorp",
        decision=ApprovalDecisionEnum.pending.value,
        created_at=now_utc,
    )
    db_session.add_all([task_cust, task_fail, approval])
    db_session.commit()

    service = DailySummaryService()
    summary = service.generate_summary(db=db_session, target_date=test_date, force_regenerate=True)

    cust_ops = summary.customer_operations
    assert len(cust_ops["enquiries"]) >= 1
    assert "Acme Corp" in cust_ops["enquiries"][0]["description"] or "Acme Corp" in cust_ops["enquiries"][0]["title"]

    assert len(cust_ops["unresolved_issues"]) >= 1
    assert "CRM API key expired" in cust_ops["unresolved_issues"][0]["error"]

    # Verify pending approvals
    assert len(summary.pending_approvals) >= 1
    assert summary.pending_approvals[0]["action_type"] == "credit_note_issue"

    # Verify recommended priorities reflect urgent pending approvals and failures
    priorities_text = " ".join(summary.recommended_priorities)
    assert "pending agent action" in priorities_text.lower()
    assert "remediate" in priorities_text.lower() or "failure" in priorities_text.lower()


def test_unconfigured_delivery_channel_graceful_handling(db_session: Session):
    """Test that selecting email or webhook without configured targets is handled gracefully."""
    test_date = date(2026, 4, 1)
    custom_settings = Settings(
        summary_delivery_channel="email",
        summary_delivery_email=None,  # Unconfigured!
        summary_webhook_url=None,     # Unconfigured!
    )
    service = DailySummaryService(app_settings=custom_settings)

    # 1. Email unconfigured
    summary_email = service.generate_summary(
        db=db_session,
        target_date=test_date,
        force_regenerate=True,
        delivery_channel="email"
    )
    assert summary_email.delivery_status == "delivery_unconfigured"
    assert "summary_delivery_email' is not configured" in summary_email.delivery_error
    assert summary_email.raw_content is not None

    # 2. Webhook unconfigured
    summary_webhook = service.generate_summary(
        db=db_session,
        target_date=test_date,
        force_regenerate=True,
        delivery_channel="webhook"
    )
    assert summary_webhook.delivery_status == "delivery_unconfigured"
    assert "summary_webhook_url' is not configured" in summary_webhook.delivery_error


def test_api_summary_endpoints(client: TestClient):
    """Test REST API routes for daily summaries."""
    # 1. Config endpoint
    resp_cfg = client.get("/api/v1/agents/summaries/config")
    assert resp_cfg.status_code == 200
    cfg = resp_cfg.json()
    assert "schedule_time" in cfg
    assert "timezone" in cfg
    assert "delivery_channel" in cfg

    # 2. Generate endpoint
    resp_gen = client.post(
        "/api/v1/agents/summaries/generate",
        json={"summary_date": "2026-05-15", "force_regenerate": True}
    )
    assert resp_gen.status_code == 200
    data = resp_gen.json()
    assert data["summary_date"] == "2026-05-15"
    assert "task_metrics" in data
    assert "raw_content" in data
    assert data["delivery_status"] in ("stored_locally", "delivery_unconfigured")

    # 3. List endpoint
    resp_list = client.get("/api/v1/agents/summaries")
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert list_data["total"] >= 1
    assert any(s["summary_date"] == "2026-05-15" for s in list_data["items"])

    # 4. Get by date endpoint
    resp_date = client.get("/api/v1/agents/summaries/date/2026-05-15")
    assert resp_date.status_code == 200
    assert resp_date.json()["summary_date"] == "2026-05-15"

    # 5. Non-existent date 404
    resp_404 = client.get("/api/v1/agents/summaries/date/1999-01-01")
    assert resp_404.status_code == 404

    # 6. Webhook trigger endpoint (n8n compatible)
    resp_hook = client.post(
        "/api/v1/agents/summaries/webhook",
        json={"summary_date": "2026-05-16"}
    )
    assert resp_hook.status_code == 200
    assert resp_hook.json()["summary_date"] == "2026-05-16"
