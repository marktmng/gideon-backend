"""Tests for persistent memory management and retrieval."""
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.repositories.memory_repository import MemoryRepository


def test_create_memory_success(client: TestClient):
    payload = {
        "key": "user_tone_preference",
        "content": "User prefers concise and respectful communication.",
        "category": "preference"
    }
    res = client.post("/api/v1/memories", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["key"] == "user_tone_preference"
    assert data["content"] == "User prefers concise and respectful communication."
    assert data["category"] == "preference"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_memory_validation_error(client: TestClient):
    # Empty content
    res = client.post("/api/v1/memories", json={"key": "test_key", "content": "   "})
    assert res.status_code in (400, 422)

    # Empty key
    res = client.post("/api/v1/memories", json={"key": "   ", "content": "Some content"})
    assert res.status_code in (400, 422)


def test_list_memories_pagination_and_filtering(client: TestClient):
    # Create two memories in different categories
    client.post("/api/v1/memories", json={
        "key": "ship_speed",
        "content": "Waverider cruising speed is Mach 12.",
        "category": "technical"
    })
    client.post("/api/v1/memories", json={
        "key": "captain_name",
        "content": "Sara Lance commands the Waverider.",
        "category": "mission"
    })

    # List all
    res = client.get("/api/v1/memories?page=1&limit=50")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 2

    # Filter by category
    filter_res = client.get("/api/v1/memories?category=technical")
    assert filter_res.status_code == 200
    items = filter_res.json()["items"]
    assert all(item["category"] == "technical" for item in items)


def test_get_memory_by_id(client: TestClient):
    create_res = client.post("/api/v1/memories", json={
        "key": "temporal_zone",
        "content": "Temporal Zone coordinates require chronal shielding.",
        "category": "technical"
    })
    mem_id = create_res.json()["id"]

    get_res = client.get(f"/api/v1/memories/{mem_id}")
    assert get_res.status_code == 200
    assert get_res.json()["key"] == "temporal_zone"


def test_get_nonexistent_memory(client: TestClient):
    random_id = str(uuid.uuid4())
    res = client.get(f"/api/v1/memories/{random_id}")
    assert res.status_code == 404


def test_update_memory(client: TestClient):
    create_res = client.post("/api/v1/memories", json={
        "key": "original_key",
        "content": "Original text content.",
        "category": "general"
    })
    mem_id = create_res.json()["id"]

    update_res = client.patch(f"/api/v1/memories/{mem_id}", json={
        "key": "updated_key",
        "content": "Updated text content.",
        "category": "preference"
    })
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["key"] == "updated_key"
    assert updated_data["content"] == "Updated text content."
    assert updated_data["category"] == "preference"


def test_delete_memory(client: TestClient):
    create_res = client.post("/api/v1/memories", json={
        "key": "temporary_directive",
        "content": "Will be purged shortly.",
        "category": "mission"
    })
    mem_id = create_res.json()["id"]

    del_res = client.delete(f"/api/v1/memories/{mem_id}")
    assert del_res.status_code == 204

    # Verify 404 after deletion
    check_res = client.get(f"/api/v1/memories/{mem_id}")
    assert check_res.status_code == 404


def test_keyword_memory_retrieval(db_session: Session):
    repo = MemoryRepository(db_session)

    # Insert test memories
    mem1 = repo.create(
        key="quantum_entanglement",
        content="Sub-space quantum entanglement allows instantaneous communication.",
        category="technical"
    )
    mem2 = repo.create(
        key="morning_beverage",
        content="User drinks black coffee without sugar.",
        category="preference"
    )
    db_session.commit()

    # Search query about quantum
    results = repo.search_relevant_memories(query="Gideon, analyze the quantum entanglement state.", limit=5)
    result_keys = [m.key for m in results]
    assert "quantum_entanglement" in result_keys
    # Irrelevant memory should not be returned
    assert "morning_beverage" not in result_keys

    # Search query about coffee
    coffee_results = repo.search_relevant_memories(query="Prepare coffee for the morning.", limit=5)
    coffee_keys = [m.key for m in coffee_results]
    assert "morning_beverage" in coffee_keys
    assert "quantum_entanglement" not in coffee_keys
