"""
Unit tests for Gideon Voice & Wake Word API (Phase 5 Hands-Free).
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_voice_status_endpoint():
    response = client.get("/api/v1/voice/status")
    assert response.status_code == 200
    data = response.json()
    assert data["engine"] == "web_speech_continuous_acoustic"
    assert data["default_wake_phrase"] == "Hey Gideon"
    assert "Hey Gideon" in data["supported_phrases"]
    assert "Gideon" in data["supported_phrases"]
    assert data["offline_capable"] is True
    assert data["external_api_required"] is False
    assert "stop" in data["interruption_keywords"]
    assert "halt" in data["interruption_keywords"]


def test_voice_config_endpoint():
    response = client.get("/api/v1/voice/config")
    assert response.status_code == 200
    data = response.json()
    assert data["default_phrase"] == "hey_gideon"
    phrase_ids = [p["id"] for p in data["available_phrases"]]
    assert "hey_gideon" in phrase_ids
    assert "gideon" in phrase_ids
    assert "both" in phrase_ids
    assert data["audio_cue"]["enabled"] is True
    assert data["audio_cue"]["frequencies_hz"] == [523.25, 659.25]


def test_voice_wake_valid_default_phrase():
    payload = {
        "phrase": "Hey Gideon",
        "command": None,
        "source": "web_client",
    }
    response = client.post("/api/v1/voice/wake", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "acknowledged"
    assert data["phrase"] == "Hey Gideon"
    assert data["acknowledged"] is True
    assert data["safety_passed"] is True


def test_voice_wake_single_breath_command():
    payload = {
        "phrase": "Hey Gideon",
        "command": "what is open on my screen?",
        "source": "windows_companion",
    }
    response = client.post("/api/v1/voice/wake", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "acknowledged"
    assert data["command"] == "what is open on my screen?"
    assert data["safety_passed"] is True
    assert "Directive captured" in data["message"]


def test_voice_wake_alternative_phrase():
    payload = {
        "phrase": "Gideon",
        "command": "take a screenshot",
        "source": "web_client",
    }
    response = client.post("/api/v1/voice/wake", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "acknowledged"
    assert data["safety_passed"] is True


def test_voice_wake_invalid_phrase():
    payload = {
        "phrase": "Hey Siri",
        "command": "hello",
    }
    response = client.post("/api/v1/voice/wake", json=payload)
    assert response.status_code == 400
    assert "Invalid wake phrase" in response.json()["detail"]


def test_voice_wake_dangerous_command_rejected():
    payload = {
        "phrase": "Hey Gideon",
        "command": "format c: /q",
    }
    response = client.post("/api/v1/voice/wake", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["safety_passed"] is False
    assert "Banned dangerous system command" in data["message"]


def test_voice_transcribe_empty_payload():
    response = client.post("/api/v1/voice/transcribe", json={"audio_base64": ""})
    assert response.status_code == 400
    assert "No audio payload" in response.json()["detail"]


def test_voice_transcribe_invalid_base64():
    response = client.post("/api/v1/voice/transcribe", json={"audio_base64": "not_valid_base64!!!"})
    assert response.status_code in [200, 400]


