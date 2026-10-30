"""Unit tests for Gideon Tools, Security Boundaries, and Approval Manager."""
import pytest
import uuid
from app.agents.tools.registry import ToolRegistry
from app.agents.tools.builtins import (
    WorkspaceListFilesTool,
    WorkspaceReadFileTool,
    DraftEmailTool,
    SendEmailTool,
    _validate_safe_path,
)
from app.agents.approval.manager import ApprovalManager
from app.schemas.agent import ToolPermissionLevel, ApprovalDecisionEnum


@pytest.mark.asyncio
async def test_tool_registry_initialization():
    registry = ToolRegistry()
    tools = registry.list_tools()
    tool_ids = {t.tool_id for t in tools}

    expected = {
        "tool_workspace_list_files",
        "tool_workspace_read_file",
        "tool_workspace_propose_diff",
        "tool_list_directive_tasks",
        "tool_create_directive_task",
        "tool_search_memories",
        "tool_research_fetch",
        "tool_draft_email",
        "tool_send_email",
        "tool_desktop_action",
    }
    assert expected.issubset(tool_ids)


def test_directory_traversal_protection():
    with pytest.raises(PermissionError) as excinfo:
        _validate_safe_path("../../../../../etc/passwd")
    assert "Directory traversal detected" in str(excinfo.value)

    with pytest.raises(PermissionError) as excinfo:
        _validate_safe_path("..\\..\\Windows\\System32\\cmd.exe")
    assert "Directory traversal detected" in str(excinfo.value)


def test_sensitive_file_protection():
    with pytest.raises(PermissionError) as excinfo:
        _validate_safe_path(".env")
    assert "sensitive file" in str(excinfo.value)


@pytest.mark.asyncio
async def test_draft_email_does_not_send():
    tool = DraftEmailTool()
    res = await tool.execute({
        "recipient": "test@example.com",
        "subject": "Hello",
        "body": "Test message"
    })
    assert res["status"] == "draft_prepared"
    assert res["requires_user_approval_to_send"] is True


def test_approval_manager_consequential_check():
    registry = ToolRegistry()
    manager = ApprovalManager(registry)

    # Read-only tool does not require approval
    assert manager.requires_approval("tool_workspace_list_files") is False
    # Local change does not require approval
    assert manager.requires_approval("tool_draft_email") is False
    # Consequential action strictly requires approval
    assert manager.requires_approval("tool_send_email") is True


def test_approval_decision_and_bound_parameters():
    registry = ToolRegistry()
    manager = ApprovalManager(registry)

    task_id = uuid.uuid4()
    approval = manager.create_approval_request(
        task_id=task_id,
        step_id=uuid.uuid4(),
        agent_id="agent_email",
        action_type="Send Email Message",
        description="Send message to client",
        target_resource="tool_send_email",
        parameters={"recipient": "client@example.com", "subject": "Contract"},
    )
    assert approval.decision == ApprovalDecisionEnum.pending.value

    # Mismatch action should raise ValueError
    with pytest.raises(ValueError):
        manager.validate_and_apply_decision(
            approval=approval,
            decision=ApprovalDecisionEnum.approved,
            bound_action="Different Action",
        )

    # Correct match applies decision
    updated = manager.validate_and_apply_decision(
        approval=approval,
        decision=ApprovalDecisionEnum.approved,
        bound_action="Send Email Message",
        bound_target="tool_send_email",
    )
    assert updated.decision == ApprovalDecisionEnum.approved.value
    assert updated.decided_at is not None

