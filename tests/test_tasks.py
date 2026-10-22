"""Tests for task endpoints."""
import uuid
from fastapi.testclient import TestClient


def test_create_task_success(client: TestClient):
    payload = {
        "title": "Recalibrate Temporal Core",
        "description": "Align flux coils with the Waverider sub-systems.",
        "priority": "high"
    }
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] == payload["title"]
    assert data["description"] == payload["description"]
    assert data["priority"] == "high"
    assert data["status"] == "pending"
    assert data["completed_at"] is None


def test_list_tasks_and_filter_status(client: TestClient):
    # Create one pending and one in_progress
    client.post("/api/v1/tasks", json={"title": "Pending Task", "priority": "low"})
    create_res = client.post("/api/v1/tasks", json={"title": "In Progress Task", "priority": "medium"})
    task_id = create_res.json()["id"]

    # Update second task to in_progress
    client.patch(f"/api/v1/tasks/{task_id}", json={"status": "in_progress"})

    # Filter by in_progress
    res = client.get("/api/v1/tasks?status=in_progress")
    assert res.status_code == 200
    data = res.json()
    assert any(t["id"] == task_id for t in data["items"])
    assert all(t["status"] == "in_progress" for t in data["items"])


def test_update_task_completed_status(client: TestClient):
    create_res = client.post("/api/v1/tasks", json={"title": "Complete Me"})
    task_id = create_res.json()["id"]

    # Mark as completed
    patch_res = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "completed"})
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["status"] == "completed"
    assert data["completed_at"] is not None

    # Reopen to pending
    reopen_res = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "pending"})
    assert reopen_res.status_code == 200
    assert reopen_res.json()["status"] == "pending"
    assert reopen_res.json()["completed_at"] is None


def test_delete_task(client: TestClient):
    create_res = client.post("/api/v1/tasks", json={"title": "Delete Me"})
    task_id = create_res.json()["id"]

    del_res = client.delete(f"/api/v1/tasks/{task_id}")
    assert del_res.status_code == 204

    get_res = client.get(f"/api/v1/tasks/{task_id}")
    assert get_res.status_code == 404


def test_task_invalid_priority_validation(client: TestClient):
    res = client.post("/api/v1/tasks", json={"title": "Bad Task", "priority": "super-critical"})
    assert res.status_code == 422


def test_get_nonexistent_task(client: TestClient):
    random_uuid = str(uuid.uuid4())
    res = client.get(f"/api/v1/tasks/{random_uuid}")
    assert res.status_code == 404
