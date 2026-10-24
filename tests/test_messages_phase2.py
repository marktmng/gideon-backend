"""Tests for Phase 2 message context ordering, streaming responses, and assistant diagnostics."""
import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.api.dependencies import get_assistant_service
from app.core.config import settings
from app.core.exceptions import AIProviderError
from app.main import app
from app.models.message import Message
from app.repositories.message_repository import MessageRepository
from app.services.assistant_service import AssistantService


def test_most_recent_messages_selected_in_chronological_order(db_session: Session):
    repo = MessageRepository(db_session)
    conv_id = uuid.uuid4()

    # Create 10 messages sequentially with distinct chronological timestamps
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(10):
        msg = Message(
            conversation_id=conv_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message number {i}",
            created_at=base_time + timedelta(seconds=i)
        )
        db_session.add(msg)
    db_session.commit()

    # Retrieve context bounded to 5 messages
    context = repo.get_recent_messages_for_context(conversation_id=conv_id, limit=5)
    assert len(context) == 5

    # Should be the last 5 messages (numbers 5, 6, 7, 8, 9) in chronological order
    contents = [m.content for m in context]
    expected = [f"Message number {i}" for i in range(5, 10)]
    assert contents == expected


def test_context_is_bounded_by_configured_limit(db_session: Session):
    repo = MessageRepository(db_session)
    conv_id = uuid.uuid4()

    # Create 30 messages with distinct chronological timestamps
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(30):
        msg = Message(
            conversation_id=conv_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Msg {i}",
            created_at=base_time + timedelta(seconds=i)
        )
        db_session.add(msg)
    db_session.commit()

    context = repo.get_recent_messages_for_context(conversation_id=conv_id, limit=settings.ai_max_context_messages)
    assert len(context) == settings.ai_max_context_messages
    assert context[-1].content == "Msg 29"


def test_failed_generation_preserves_user_message_without_fake_reply(client: TestClient):
    conv_res = client.post("/api/v1/conversations", json={})
    conv_id = conv_res.json()["id"]

    # Mock assistant service to raise AIProviderError
    mock_service = MagicMock(spec=AssistantService)
    mock_service.generate_response.side_effect = AIProviderError("Simulated upstream provider outage")
    app.dependency_overrides[get_assistant_service] = lambda: mock_service

    try:
        res = client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"content": "Important instruction that must not be lost"}
        )
        assert res.status_code == 502
        assert "Simulated upstream provider outage" in res.json()["detail"]

        # Verify user message remains safely stored in database
        list_res = client.get(f"/api/v1/conversations/{conv_id}/messages")
        assert list_res.status_code == 200
        items = list_res.json()["items"]
        assert len(items) == 1
        assert items[0]["role"] == "user"
        assert items[0]["content"] == "Important instruction that must not be lost"
        # No assistant reply was fabricated!
    finally:
        app.dependency_overrides.pop(get_assistant_service, None)


def test_streaming_message_event_sequence(client: TestClient):
    conv_res = client.post("/api/v1/conversations", json={})
    conv_id = conv_res.json()["id"]

    # Post message to stream endpoint
    res = client.post(
        f"/api/v1/conversations/{conv_id}/messages/stream",
        json={"content": "Gideon, stream your status report."}
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

    # Parse SSE stream
    stream_text = res.text
    blocks = [b.strip() for b in stream_text.split("\n\n") if b.strip()]

    events = []
    for block in blocks:
        lines = block.split("\n")
        event_name = None
        data_str = None
        for line in lines:
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_str = line.split(":", 1)[1].strip()
        if event_name and data_str:
            events.append((event_name, json.loads(data_str)))

    # Verify event types in sequence
    event_names = [e[0] for e in events]
    assert "start" in event_names
    assert "delta" in event_names
    assert "complete" in event_names

    # Check start event
    start_payload = next(e[1] for e in events if e[0] == "start")
    assert start_payload["conversation_id"] == conv_id
    assert "user_message" in start_payload

    # Check complete event
    complete_payload = next(e[1] for e in events if e[0] == "complete")
    assert "assistant_message" in complete_payload
    assert complete_payload["assistant_message"]["role"] == "assistant"

    # Verify assistant message is persisted in conversation history
    list_res = client.get(f"/api/v1/conversations/{conv_id}/messages")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) == 2  # user + assistant


def test_streaming_to_nonexistent_conversation_returns_404(client: TestClient):
    random_id = str(uuid.uuid4())
    res = client.post(
        f"/api/v1/conversations/{random_id}/messages/stream",
        json={"content": "Hello"}
    )
    assert res.status_code == 404


def test_streaming_empty_content_returns_400(client: TestClient):
    conv_res = client.post("/api/v1/conversations", json={})
    conv_id = conv_res.json()["id"]

    res = client.post(
        f"/api/v1/conversations/{conv_id}/messages/stream",
        json={"content": "   "}
    )
    assert res.status_code in (400, 422)


def test_streaming_error_emits_error_event_without_corrupting_database(client: TestClient):
    conv_res = client.post("/api/v1/conversations", json={})
    conv_id = conv_res.json()["id"]

    mock_service = MagicMock(spec=AssistantService)

    async def mock_failing_stream(*args, **kwargs):
        raise AIProviderError("Mid-stream connection drop")
        yield "Never reached"  # generator syntax

    mock_service.generate_stream = mock_failing_stream
    app.dependency_overrides[get_assistant_service] = lambda: mock_service

    try:
        res = client.post(
            f"/api/v1/conversations/{conv_id}/messages/stream",
            json={"content": "Stream test that should fail"}
        )
        assert res.status_code == 200

        stream_text = res.text
        assert "event: error" in stream_text
        assert "Mid-stream connection drop" in stream_text

        # Verify only user message exists (no partial assistant message persisted)
        list_res = client.get(f"/api/v1/conversations/{conv_id}/messages")
        items = list_res.json()["items"]
        assert len(items) == 1
        assert items[0]["role"] == "user"
    finally:
        app.dependency_overrides.pop(get_assistant_service, None)


def test_assistant_status_diagnostics_no_secret_leak(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "super-secret-production-key-999")

    res = client.get("/api/v1/assistant/status")
    assert res.status_code == 200
    data = res.json()

    # Secret key must NEVER appear in the response payload
    raw_response = res.text
    assert "super-secret-production-key-999" not in raw_response

    # Verify diagnostic fields
    assert "provider" in data
    assert "is_demo" in data
    assert "status" in data
    assert "streaming_supported" in data
    assert "memory_enabled" in data
    assert "database_connected" in data
    assert data["memory_enabled"] is True
    assert data["streaming_supported"] is True
