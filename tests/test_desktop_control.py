"""Unit and API integration tests for Phase 4 Windows Desktop Control."""
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.desktop.schemas import (
    DesktopActionType,
    TaskLifecycleStatus,
    RiskLevel,
    OpenUrlParams,
    OpenDirectoryParams,
)
from app.desktop.security import DesktopSecurityPolicy
from app.desktop.adapter import MockDesktopAdapter
from app.desktop.registry import DesktopActionRegistry
from app.desktop.service import DesktopTaskService
from app.desktop.ai_tool_bridge import DesktopIntentBridge
from app.api.dependencies import get_desktop_service

client = TestClient(app)


def test_action_registry_contains_all_core_actions():
    registry = DesktopActionRegistry()
    actions = registry.list_actions()

    assert DesktopActionType.open_application in actions
    assert DesktopActionType.open_url in actions
    assert DesktopActionType.open_directory in actions
    assert DesktopActionType.open_file_explorer in actions
    assert DesktopActionType.inspect_active_window in actions
    assert DesktopActionType.type_text in actions
    assert DesktopActionType.press_shortcut in actions
    assert DesktopActionType.capture_screenshot in actions


def test_security_policy_application_allowlist():
    policy = DesktopSecurityPolicy()

    # Allowlisted applications
    valid, _, meta = policy.validate_application_name("notepad")
    assert valid is True
    assert meta["binary"] == "notepad.exe"

    valid_calc, _, _ = policy.validate_application_name("calculator")
    assert valid_calc is True

    valid_browser, _, _ = policy.validate_application_name("browser")
    assert valid_browser is True

    # Disallowed applications / arbitrary commands
    invalid, msg, _ = policy.validate_application_name("powershell_malicious")
    assert invalid is False
    assert "not in the trusted allowlist" in msg

    invalid_cmd, _, _ = policy.validate_application_name("format_c")
    assert invalid_cmd is False


def test_security_policy_url_validation():
    policy = DesktopSecurityPolicy()

    valid, _ = policy.validate_url("https://21st.dev/components")
    assert valid is True

    valid_http, _ = policy.validate_url("http://localhost:3000")
    assert valid_http is True

    # Disallowed schemes
    file_scheme, msg = policy.validate_url("file:///C:/Windows/System32/cmd.exe")
    assert file_scheme is False
    assert "Disallowed URL scheme" in msg

    js_scheme, _ = policy.validate_url("javascript:alert(1)")
    assert js_scheme is False

    # Disallowed injection characters
    injection, _ = policy.validate_url("https://example.com; rm -rf /")
    assert injection is False


def test_security_policy_directory_allowlist_and_traversal_protection():
    policy = DesktopSecurityPolicy(workspace_root=Path("C:/Mark/Gideon"))

    # Traversal rejected
    traversal, msg, _ = policy.validate_directory_path("../../../Windows")
    assert traversal is False
    assert "traversal" in msg.lower()

    # Disallowed system boundaries
    sys_dir, msg2, _ = policy.validate_directory_path("C:/Windows/System32")
    assert sys_dir is False

    # Allowed workspace or user Desktop
    if Path("C:/Mark/Gideon").exists():
        valid_dir, _, can_path = policy.validate_directory_path("C:/Mark/Gideon")
        assert valid_dir is True
        assert can_path is not None


def test_security_policy_shortcuts():
    policy = DesktopSecurityPolicy()

    assert policy.validate_shortcut("Ctrl+C")[0] is True
    assert policy.validate_shortcut("Ctrl+V")[0] is True
    assert policy.validate_shortcut("Enter")[0] is True
    assert policy.validate_shortcut("Escape")[0] is True

    # Dangerous shortcuts
    assert policy.validate_shortcut("Win+R")[0] is False
    assert policy.validate_shortcut("Alt+F4")[0] is False


def test_security_policy_sensitive_window_detection():
    policy = DesktopSecurityPolicy()

    # Sensitive window titles
    assert policy.check_target_window_safety("Administrator: Windows PowerShell")[0] is False
    assert policy.check_target_window_safety("Registry Editor")[0] is False
    assert policy.check_target_window_safety("Task Manager")[0] is False

    # Safe window
    assert policy.check_target_window_safety("Untitled - Notepad", "notepad.exe")[0] is True


def test_desktop_service_lifecycle_low_risk_auto_executes():
    mock_adapter = MockDesktopAdapter()
    service = DesktopTaskService(adapter=mock_adapter)

    task = service.create_task(
        action=DesktopActionType.open_application,
        params={"app_name": "notepad"},
    )

    assert task.status == TaskLifecycleStatus.completed
    assert task.risk_level == RiskLevel.low
    assert task.requires_confirmation is False
    assert task.result is not None
    assert task.result["app_name"] == "notepad"
    assert len(mock_adapter.calls) == 1
    assert mock_adapter.calls[0]["action"] == "open_application"


def test_desktop_service_lifecycle_medium_risk_requires_confirmation():
    mock_adapter = MockDesktopAdapter()
    service = DesktopTaskService(adapter=mock_adapter)

    # Creating medium risk task requires confirmation
    task = service.create_task(
        action=DesktopActionType.type_text,
        params={"target_window": "Document - Notepad", "text": "Hello Gideon"},
    )

    assert task.status == TaskLifecycleStatus.awaiting_confirmation
    assert task.risk_level == RiskLevel.medium
    assert task.requires_confirmation is True
    assert len(mock_adapter.calls) == 0  # Not executed yet!

    # Confirming executes the action
    confirmed_task = service.confirm_task(task.id, confirmed=True)
    assert confirmed_task.status == TaskLifecycleStatus.completed
    assert confirmed_task.result["characters_typed"] == 12
    assert len(mock_adapter.calls) == 1


def test_desktop_service_confirmation_rejection_cancels_task():
    mock_adapter = MockDesktopAdapter()
    service = DesktopTaskService(adapter=mock_adapter)

    task = service.create_task(
        action=DesktopActionType.press_shortcut,
        params={"target_window": "Document - Notepad", "shortcut": "Ctrl+S"},
    )

    assert task.status == TaskLifecycleStatus.awaiting_confirmation

    rejected_task = service.confirm_task(task.id, confirmed=False, reason="User cancelled confirmation")
    assert rejected_task.status == TaskLifecycleStatus.cancelled
    assert "User cancelled" in rejected_task.error
    assert len(mock_adapter.calls) == 0  # Kept safe, never touched mock


def test_desktop_service_global_stop_control():
    mock_adapter = MockDesktopAdapter()
    service = DesktopTaskService(adapter=mock_adapter)

    # Create two pending tasks
    task1 = service.create_task(
        action=DesktopActionType.type_text,
        params={"target_window": "Win1", "text": "Sample"},
    )
    task2 = service.create_task(
        action=DesktopActionType.press_shortcut,
        params={"target_window": "Win2", "shortcut": "Enter"},
    )

    assert task1.status == TaskLifecycleStatus.awaiting_confirmation
    assert task2.status == TaskLifecycleStatus.awaiting_confirmation

    stop_res = service.stop_all()
    assert stop_res.stopped is True
    assert stop_res.tasks_cancelled == 2

    # Verify task states are now cancelled
    assert service.get_task(task1.id).status == TaskLifecycleStatus.cancelled
    assert service.get_task(task2.id).status == TaskLifecycleStatus.cancelled


def test_desktop_intent_bridge_commands():
    mock_adapter = MockDesktopAdapter()
    service = DesktopTaskService(adapter=mock_adapter)
    bridge = DesktopIntentBridge(desktop_service=service)

    # 1. Open Explorer
    reply, data = bridge.try_handle_desktop_intent("Gideon, open File Explorer please")
    assert "File Explorer" in reply
    assert data is not None

    # 2. Open Browser
    reply2, data2 = bridge.try_handle_desktop_intent("open my browser")
    assert "browser" in reply2.lower()

    # 3. Global Stop
    reply3, data3 = bridge.try_handle_desktop_intent("Gideon, emergency stop!")
    assert "Global stop engaged" in reply3

    # 4. Normal query returns None (allowing regular LLM conversation)
    assert bridge.try_handle_desktop_intent("What is the capital of France?") is None


# ============================================================================
# API Route Integration Tests
# ============================================================================

def test_api_desktop_actions_list():
    response = client.get("/api/v1/desktop/actions")
    assert response.status_code == 200
    actions = response.json()
    assert len(actions) >= 8
    action_types = [a["action"] for a in actions]
    assert "open_application" in action_types
    assert "open_url" in action_types
    assert "type_text" in action_types


def test_api_desktop_active_window():
    response = client.get("/api/v1/desktop/active-window")
    assert response.status_code == 200
    data = response.json()
    assert "hwnd" in data
    assert "title" in data
    assert "process_name" in data


def test_api_desktop_create_and_confirm_task():
    # Use mock service for isolated API test
    mock_adapter = MockDesktopAdapter()
    test_service = DesktopTaskService(adapter=mock_adapter)
    app.dependency_overrides[get_desktop_service] = lambda: test_service

    try:
        # Create medium-risk task
        res = client.post(
            "/api/v1/desktop/tasks",
            json={
                "action": "type_text",
                "params": {"target_window": "Notepad", "text": "Test via API"}
            }
        )
        assert res.status_code == 201
        task_data = res.json()
        task_id = task_data["id"]
        assert task_data["status"] == "awaiting_confirmation"

        # Confirm task
        confirm_res = client.post(
            f"/api/v1/desktop/tasks/{task_id}/confirm",
            json={"confirmed": True}
        )
        assert confirm_res.status_code == 200
        confirmed_data = confirm_res.json()
        assert confirmed_data["status"] == "completed"
        assert confirmed_data["result"]["characters_typed"] == 12

        # List tasks
        list_res = client.get("/api/v1/desktop/tasks")
        assert list_res.status_code == 200
        assert list_res.json()["total"] >= 1

        # Global stop
        stop_res = client.post("/api/v1/desktop/stop")
        assert stop_res.status_code == 200
        assert stop_res.json()["stopped"] is True
    finally:
        app.dependency_overrides.pop(get_desktop_service, None)


def test_api_desktop_rejects_unknown_action():
    res = client.post(
        "/api/v1/desktop/tasks",
        json={"action": "rmdir_all", "params": {}}
    )
    assert res.status_code == 422  # Pydantic enum validation failure


def test_security_policy_system_subdirectory_forbidden():
    policy = DesktopSecurityPolicy(workspace_root=Path("C:/Mark/Gideon"))
    # System subdirectory must be rejected
    is_valid, msg, _ = policy.validate_directory_path("C:/Windows/System32/drivers")
    assert is_valid is False
    assert "restricted" in msg.lower() or "outside" in msg.lower()


def test_security_policy_application_arguments_validation():
    policy = DesktopSecurityPolicy()
    # Shell escapes in args must fail
    ok, msg = policy.validate_application_arguments("notepad", ["file.txt; rm -rf /"])
    assert ok is False
    assert "disallowed" in msg.lower()

    # Path traversal in args must fail
    ok, msg = policy.validate_application_arguments("notepad", ["../../secret.txt"])
    assert ok is False
    assert "traversal" in msg.lower()

    # Valid simple filename
    ok, _ = policy.validate_application_arguments("notepad", ["notes.txt"])
    assert ok is True


def test_confirmation_authorization_binding():
    mock_adapter = MockDesktopAdapter()
    test_service = DesktopTaskService(adapter=mock_adapter)
    app.dependency_overrides[get_desktop_service] = lambda: test_service

    try:
        task = test_service.create_task(
            action=DesktopActionType.type_text,
            params={"target_window": "Notepad", "text": "Authorization binding test"}
        )
        task_id = task.id

        # Attempt to confirm with mismatched action
        mismatched_res = client.post(
            f"/api/v1/desktop/tasks/{task_id}/confirm",
            json={
                "confirmed": True,
                "action": "open_application",  # Mismatch!
                "target": "Notepad"
            }
        )
        assert mismatched_res.status_code == 400
        assert "mismatch" in mismatched_res.json()["detail"].lower()

        # Confirm with correct action and target
        correct_res = client.post(
            f"/api/v1/desktop/tasks/{task_id}/confirm",
            json={
                "confirmed": True,
                "action": "type_text",
                "target": "Notepad"
            }
        )
        assert correct_res.status_code == 200
        assert correct_res.json()["status"] == "completed"
    finally:
        app.dependency_overrides.pop(get_desktop_service, None)


def test_global_stop_prevents_subsequent_execution():
    mock_adapter = MockDesktopAdapter()
    test_service = DesktopTaskService(adapter=mock_adapter)

    task = test_service.create_task(
        action=DesktopActionType.type_text,
        params={"target_window": "Notepad", "text": "Halt test"}
    )
    task_id = task.id
    assert task.status == TaskLifecycleStatus.awaiting_confirmation

    # Initiate global stop
    stop_resp = test_service.stop_all()
    assert stop_resp.stopped is True
    assert stop_resp.tasks_cancelled >= 1

    # Attempt to confirm stopped task
    import pytest
    with pytest.raises(ValueError) as excinfo:
        test_service.confirm_task(task_id, confirmed=True)
    assert "cannot be confirmed" in str(excinfo.value).lower()

