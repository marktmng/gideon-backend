"""Integration tests for Phase 5 AI Agents API endpoints."""
import pytest
from fastapi.testclient import TestClient


def test_api_list_agents(client: TestClient):
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 6
    agent_ids = {a["agent_id"] for a in data["items"]}
    assert "agent_research" in agent_ids
    assert "agent_coding" in agent_ids
    assert "agent_email" in agent_ids


def test_api_list_tools(client: TestClient):
    response = client.get("/api/v1/agents/tools")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 8
    tool_ids = {t["tool_id"] for t in data["items"]}
    assert "tool_workspace_list_files" in tool_ids
    assert "tool_send_email" in tool_ids


def test_api_create_and_get_task(client: TestClient):
    payload = {
        "title": "Code Analysis Task",
        "user_request": "Review python source files and propose optimizations",
        "assigned_agent_id": "agent_coding"
    }
    create_resp = client.post("/api/v1/agents/tasks", json=payload)
    assert create_resp.status_code == 201
    task_data = create_resp.json()
    task_id = task_data["id"]
    assert task_data["title"] == "Code Analysis Task"
    assert len(task_data["steps"]) >= 1

    # Get task detail
    get_resp = client.get(f"/api/v1/agents/tasks/{task_id}")
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["id"] == task_id
    assert "steps" in detail

    # Get task progress
    prog_resp = client.get(f"/api/v1/agents/tasks/{task_id}/progress")
    assert prog_resp.status_code == 200
    prog = prog_resp.json()
    assert "progress_percent" in prog
    assert prog["task_id"] == task_id


def test_api_cancel_task(client: TestClient):
    payload = {
        "title": "Cancellable Task",
        "user_request": "Plan a long running multi-stage initiative",
        "assigned_agent_id": "agent_productivity"
    }
    create_resp = client.post("/api/v1/agents/tasks", json=payload)
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    cancel_resp = client.post(f"/api/v1/agents/tasks/{task_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_api_list_tasks_pagination(client: TestClient):
    resp = client.get("/api/v1/agents/tasks?page=1&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["page"] == 1
    assert data["limit"] == 10


def test_api_approval_shortcuts_require_pending_approval(client: TestClient):
    # If no pending approval exists, 400 is returned
    payload = {
        "title": "Simple Task",
        "user_request": "List workspace files",
        "assigned_agent_id": "agent_coding"
    }
    create_resp = client.post("/api/v1/agents/tasks", json=payload)
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # Trying to approve when no approval is pending
    approve_resp = client.post(f"/api/v1/agents/tasks/{task_id}/approve")
    assert approve_resp.status_code == 400
    assert "No pending approval" in approve_resp.json()["detail"]


def test_api_approval_lifecycle_and_decision_flow(client: TestClient, db_session):
    # Create task with email agent that has a consequential send_email step
    payload = {
        "title": "Outreach Correspondence",
        "user_request": "Draft and send email to vip@example.com",
        "assigned_agent_id": "agent_email"
    }
    create_resp = client.post("/api/v1/agents/tasks", json=payload)
    assert create_resp.status_code == 201
    task = create_resp.json()
    task_id = task["id"]

    # Consequential step has requires_approval=True
    consequential_step = next(s for s in task["steps"] if s["requires_approval"])
    assert consequential_step["tool_id"] == "tool_send_email"

    # Manually create approval on the test database session to simulate engine pause
    from app.repositories.agent_repository import AgentRepository
    from app.services.agent_service import AgentService
    import uuid

    repo = AgentRepository(db_session)
    service = AgentService()
    approval = service.approval_manager.create_approval_request(
        task_id=uuid.UUID(task_id),
        step_id=uuid.UUID(consequential_step["id"]),
        agent_id="agent_email",
        action_type="Send Email Message",
        description="Send email to vip@example.com",
        target_resource="tool_send_email",
        parameters={"recipient": "vip@example.com"},
    )
    repo.create_approval(approval)
    repo.update_task_status(uuid.UUID(task_id), "awaiting_approval")
    repo.update_step_status(uuid.UUID(consequential_step["id"]), "awaiting_approval")
    db_session.commit()

    # 1. Query progress shows pending approval
    prog_resp = client.get(f"/api/v1/agents/tasks/{task_id}/progress")
    assert prog_resp.status_code == 200
    assert prog_resp.json()["pending_approval_id"] == str(approval.id)

    # 2. Reject decision via API
    reject_resp = client.post(
        f"/api/v1/agents/tasks/{task_id}/approvals/{approval.id}",
        json={"decision": "rejected", "reason": "Test rejection"}
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["approval"]["decision"] == "rejected"
    assert reject_resp.json()["task_status"] == "failed"

    # 3. Attempting to approve after already decided returns 400
    redecide_resp = client.post(
        f"/api/v1/agents/tasks/{task_id}/approvals/{approval.id}",
        json={"decision": "approved"}
    )
    assert redecide_resp.status_code == 400


