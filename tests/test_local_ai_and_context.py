"""Unit and integration tests for Local-First AI (Ollama) and PC Context Awareness."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.core.config import settings
from app.ai.ollama_provider import OllamaAIProvider
from app.ai.provider_factory import AIProviderFactory
from app.services.assistant_service import AssistantService
from app.services.local_context_service import LocalContextService
from app.services.local_monitoring_service import LocalMonitoringService
from app.desktop.ai_tool_bridge import DesktopIntentBridge
from app.models.agent import AgentTask, AgentApproval
from app.schemas.agent import TaskStatusEnum, ApprovalDecisionEnum


def test_ollama_provider_offline_check():
    # Use unreachable port to test offline error handling and setup instructions deterministically
    provider = OllamaAIProvider(base_url="http://127.0.0.1:59999", model="llama3.2")
    assert provider.name == "ollama"
    assert provider.is_demo is False
    assert provider.supports_streaming is True

    # When Ollama is not running
    status = provider.check_connection()
    assert status["connected"] is False
    assert "setup_instructions" in status
    assert len(status["setup_instructions"]) >= 3


def test_ollama_provider_mocked_success():
    provider = OllamaAIProvider(base_url="http://127.0.0.1:11434", model="llama3.2")
    
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "message": {"role": "assistant", "content": "I am running locally on your PC via Ollama."}
        }
        mock_client.post.return_value = mock_res
        mock_client_cls.return_value = mock_client

        response = provider.generate_response(messages=[{"role": "user", "content": "Hello local AI"}])
        assert "running locally on your PC" in response


def test_provider_factory_and_assistant_switching():
    # Test factory instantiation
    ollama_provider = AIProviderFactory.get_provider("ollama")
    assert isinstance(ollama_provider, OllamaAIProvider)

    local_provider = AIProviderFactory.get_provider("local")
    assert isinstance(local_provider, OllamaAIProvider)

    # Test assistant service switching
    service = AssistantService()
    service.switch_provider("ollama", model="qwen2.5")
    status = service.get_status()
    assert status.provider == "ollama"
    assert status.status == "local_ai_active"
    assert status.has_provider_credentials is True
    assert status.model == "qwen2.5"

    # Reset back to demo
    service.switch_provider("demo")
    assert service.provider.name == "demo"
    assert service.get_status().status == "demo_mode"


def test_local_context_windows_enumeration():
    service = LocalContextService()
    windows = service.get_open_windows()
    assert isinstance(windows, list)
    if windows:
        first = windows[0]
        assert "title" in first
        assert "process_name" in first
        assert "is_active" in first


def test_local_context_active_window():
    service = LocalContextService()
    active = service.get_active_window()
    assert isinstance(active, dict)
    assert "title" in active
    assert "process_name" in active
    assert "pid" in active


def test_local_context_directory_safety_and_summary():
    service = LocalContextService()
    
    # 1. Valid workspace directory
    summary = service.summarize_directory()
    assert summary["success"] is True
    assert summary["total_files"] >= 0
    assert "path" in summary
    assert "entries_preview" in summary

    # 2. Path traversal attack prevented
    escaped = service.summarize_directory(target_path_str="C:\\Windows\\System32")
    assert escaped["success"] is False
    assert "Access denied" in escaped["error"]


def test_local_context_pending_tasks_and_approvals(db_session):
    service = LocalContextService()

    # Create test task
    task = AgentTask(
        title="Local Awareness Verification Task",
        user_request="Verify local PC context tools",
        status=TaskStatusEnum.running.value,
        assigned_agent_id="developer_agent",
    )
    db_session.add(task)
    db_session.flush()

    # Create test pending approval
    approval = AgentApproval(
        task_id=task.id,
        action_type="open_application",
        agent_id="developer_agent",
        description="Approve launching notepad",
        decision=ApprovalDecisionEnum.pending.value,
    )
    db_session.add(approval)
    db_session.commit()

    status_data = service.get_pending_tasks_and_approvals(db_session)
    assert status_data["pending_tasks_count"] >= 1
    assert status_data["pending_approvals_count"] >= 1
    assert any(t["title"] == "Local Awareness Verification Task" for t in status_data["pending_tasks"])
    assert any(a["action_type"] == "open_application" for a in status_data["pending_approvals"])


def test_desktop_intent_bridge_pc_awareness_questions(db_session):
    desktop_service = MagicMock()
    context_service = LocalContextService()
    bridge = DesktopIntentBridge(desktop_service=desktop_service, context_service=context_service, db=db_session)

    # 1. "What is open on my screen?"
    res = bridge.try_handle_desktop_intent("What is open on my screen?", db=db_session)
    assert res is not None
    reply, meta = res
    assert "Foreground Window" in reply or "No open application windows" in reply
    assert "windows" in meta

    # 2. "What tasks are still pending?"
    res = bridge.try_handle_desktop_intent("What tasks are still pending?", db=db_session)
    assert res is not None
    reply, meta = res
    assert "Gideon Task Engine Status" in reply

    # 3. "What changed since yesterday?"
    res = bridge.try_handle_desktop_intent("What changed since yesterday?", db=db_session)
    assert res is not None
    reply, meta = res
    assert "System Activity & Workspace Changes" in reply

    # 4. "Summarize this folder"
    res = bridge.try_handle_desktop_intent("Summarize this folder", db=db_session)
    assert res is not None
    reply, meta = res
    assert "Workspace Directory Summary" in reply


def test_local_monitoring_toggle_and_check(db_session):
    context_service = LocalContextService()
    monitor = LocalMonitoringService(context_service=context_service)
    
    # Toggle enabled
    state = monitor.toggle(True)
    assert state is True
    assert monitor.is_enabled is True

    # Check changes
    changes = monitor.check_changes(db=db_session)
    assert isinstance(changes, list)

    status = monitor.get_status()
    assert status["is_enabled"] is True
    assert "recent_events" in status

    # Toggle disabled
    state = monitor.toggle(False)
    assert state is False
    assert monitor.is_enabled is False


def test_local_context_api_endpoints(client: TestClient):
    # 1. Ollama status endpoint
    res = client.get("/api/v1/assistant/ollama/status")
    assert res.status_code == 200
    data = res.json()
    assert "connected" in data
    assert "base_url" in data

    # 2. Provider switch endpoint
    res = client.post("/api/v1/assistant/provider", json={"provider": "ollama", "model": "llama3.2"})
    assert res.status_code == 200
    assert res.json()["provider"] == "ollama"

    # Reset back to demo
    client.post("/api/v1/assistant/provider", json={"provider": "demo"})

    # 3. Windows enumeration endpoint
    res = client.get("/api/v1/local-context/windows")
    assert res.status_code == 200
    assert "windows" in res.json()

    # 4. Active window endpoint
    res = client.get("/api/v1/local-context/active-window")
    assert res.status_code == 200
    assert "title" in res.json()

    # 5. Tasks summary endpoint
    res = client.get("/api/v1/local-context/tasks")
    assert res.status_code == 200
    assert "pending_tasks_count" in res.json()

    # 6. Directory summary endpoint
    res = client.get("/api/v1/local-context/directory")
    assert res.status_code == 200
    assert res.json()["success"] is True

    # 7. Monitoring toggle endpoint
    res = client.post("/api/v1/local-context/monitoring/toggle", json={"enabled": True})
    assert res.status_code == 200
    assert res.json()["is_enabled"] is True
