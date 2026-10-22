"""Tests for conversation endpoints."""
import uuid
from fastapi.testclient import TestClient


def test_create_conversation_without_title(client: TestClient):
    response = client.post("/api/v1/conversations", json={})
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] is None
    assert "created_at" in data


def test_create_conversation_with_title(client: TestClient):
    response = client.post("/api/v1/conversations", json={"title": "Temporal Physics"})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Temporal Physics"


def test_list_conversations_pagination(client: TestClient):
    # Create two conversations
    client.post("/api/v1/conversations", json={"title": "Conv A"})
    client.post("/api/v1/conversations", json={"title": "Conv B"})

    response = client.get("/api/v1/conversations?page=1&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 2
    assert data["page"] == 1
    assert data["limit"] == 10


def test_get_conversation_by_id(client: TestClient):
    create_res = client.post("/api/v1/conversations", json={"title": "Specific Conv"})
    conv_id = create_res.json()["id"]

    get_res = client.get(f"/api/v1/conversations/{conv_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == conv_id
    assert get_res.json()["title"] == "Specific Conv"


def test_update_conversation_title(client: TestClient):
    create_res = client.post("/api/v1/conversations", json={"title": "Initial Title"})
    conv_id = create_res.json()["id"]

    patch_res = client.patch(f"/api/v1/conversations/{conv_id}", json={"title": "Updated Title"})
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Updated Title"


def test_delete_conversation(client: TestClient):
    create_res = client.post("/api/v1/conversations", json={"title": "To Delete"})
    conv_id = create_res.json()["id"]

    del_res = client.delete(f"/api/v1/conversations/{conv_id}")
    assert del_res.status_code == 204

    # Verify 404 after deletion
    get_res = client.get(f"/api/v1/conversations/{conv_id}")
    assert get_res.status_code == 404


def test_get_nonexistent_conversation(client: TestClient):
    random_uuid = str(uuid.uuid4())
    res = client.get(f"/api/v1/conversations/{random_uuid}")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_invalid_uuid_returns_422(client: TestClient):
    res = client.get("/api/v1/conversations/invalid-uuid-string")
    assert res.status_code == 422
