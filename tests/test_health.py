"""Tests for health and assistant status endpoints."""
from fastapi.testclient import TestClient


def test_root_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == "Gideon"
    assert "database" in data
    assert "ai_provider" in data
    assert "demo_mode" in data


def test_api_v1_health(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_assistant_status(client: TestClient):
    response = client.get("/api/v1/assistant/status")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Gideon"
    assert data["provider"] == "demo"
    assert data["is_demo"] is True
    assert "capabilities" in data
    assert len(data["capabilities"]) > 0
    assert "unconfigured_features" in data
