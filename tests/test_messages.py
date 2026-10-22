"""Tests for message submission and retrieval."""
import uuid
from fastapi.testclient import TestClient


def test_submit_message_success_in_demo_mode(client: TestClient):
    # Create conversation first
    conv_res = client.post("/api/v1/conversations", json={})
    conv_id = conv_res.json()["id"]

    # Submit user message
    msg_res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "Gideon, calculate the temporal jump trajectory."}
    )
    assert msg_res.status_code == 201
    data = msg_res.json()
    assert "user_message" in data
    assert "assistant_message" in data

    user_msg = data["user_message"]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "Gideon, calculate the temporal jump trajectory."
    assert user_msg["conversation_id"] == conv_id

    asst_msg = data["assistant_message"]
    assert asst_msg["role"] == "assistant"
    assert asst_msg["conversation_id"] == conv_id
    assert "Gideon Demo Mode" in asst_msg["content"]

    # Check that conversation title was auto-updated
    conv_check = client.get(f"/api/v1/conversations/{conv_id}")
    assert conv_check.status_code == 200
    assert conv_check.json()["title"] is not None


def test_list_messages_pagination(client: TestClient):
    conv_res = client.post("/api/v1/conversations", json={})
    conv_id = conv_res.json()["id"]

    # Submit two messages (each generates user + assistant message)
    client.post(f"/api/v1/conversations/{conv_id}/messages", json={"content": "Msg 1"})
    client.post(f"/api/v1/conversations/{conv_id}/messages", json={"content": "Msg 2"})

    list_res = client.get(f"/api/v1/conversations/{conv_id}/messages?page=1&limit=10")
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] == 4
    assert len(data["items"]) == 4


def test_submit_empty_message_validation_failure(client: TestClient):
    conv_res = client.post("/api/v1/conversations", json={})
    conv_id = conv_res.json()["id"]

    res = client.post(f"/api/v1/conversations/{conv_id}/messages", json={"content": "   "})
    assert res.status_code in (400, 422)


def test_submit_message_to_nonexistent_conversation(client: TestClient):
    random_uuid = str(uuid.uuid4())
    res = client.post(f"/api/v1/conversations/{random_uuid}/messages", json={"content": "Hello"})
    assert res.status_code == 404


def test_cascade_delete_messages(client: TestClient):
    conv_res = client.post("/api/v1/conversations", json={})
    conv_id = conv_res.json()["id"]

    client.post(f"/api/v1/conversations/{conv_id}/messages", json={"content": "Hello"})

    # Delete conversation
    del_res = client.delete(f"/api/v1/conversations/{conv_id}")
    assert del_res.status_code == 204

    # List messages for deleted conversation
    list_res = client.get(f"/api/v1/conversations/{conv_id}/messages")
    assert list_res.status_code == 404
