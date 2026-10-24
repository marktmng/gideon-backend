"""Tests for AI Provider architecture, factory, and Gemini provider implementation."""
import asyncio
from unittest.mock import MagicMock, AsyncMock
import pytest
from google.genai import types, errors
from app.ai.base import BaseAIProvider
from app.ai.demo_provider import DemoAIProvider
from app.ai.gemini_provider import GeminiAIProvider
from app.ai.provider_factory import AIProviderFactory
from app.core.config import settings
from app.core.exceptions import (
    AIConfigurationError,
    AIRateLimitError,
    AIProviderTimeoutError,
    AIProviderError,
)


def test_provider_factory_demo_mode():
    provider = AIProviderFactory.get_provider("demo")
    assert isinstance(provider, DemoAIProvider)
    assert provider.name == "demo"
    assert provider.is_demo is True
    assert provider.supports_streaming is True


def test_provider_factory_gemini_missing_credentials_raises(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "ai_api_key", None)

    with pytest.raises(AIConfigurationError) as exc_info:
        AIProviderFactory.get_provider("gemini")
    assert "no valid API key was found" in str(exc_info.value)


def test_provider_factory_unsupported_provider_raises():
    with pytest.raises(AIConfigurationError) as exc_info:
        AIProviderFactory.get_provider("unsupported_quantum_ai")
    assert "Unsupported AI provider" in str(exc_info.value)


def test_provider_factory_gemini_with_credentials(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "mock-test-key-12345")
    mock_client = MagicMock()
    provider = GeminiAIProvider(api_key="mock-test-key-12345", client=mock_client)
    assert isinstance(provider, BaseAIProvider)
    assert provider.name == "gemini"
    assert provider.is_demo is False
    assert provider.supports_streaming is True


def test_gemini_provider_format_contents():
    mock_client = MagicMock()
    provider = GeminiAIProvider(api_key="mock-key", client=mock_client)

    messages = [
        {"role": "system", "content": "Ignore this system instruction in contents"},
        {"role": "user", "content": "Hello Gideon"},
        {"role": "assistant", "content": "Greetings. How may I assist?"},
        {"role": "user", "content": "What is the Waverider status?"},
    ]

    contents = provider._format_contents(messages)
    # System role is omitted from contents because it goes in GenerateContentConfig
    assert len(contents) == 3
    assert contents[0].role == "user"
    assert contents[0].parts[0].text == "Hello Gideon"
    assert contents[1].role == "model"
    assert contents[1].parts[0].text == "Greetings. How may I assist?"
    assert contents[2].role == "user"
    assert contents[2].parts[0].text == "What is the Waverider status?"


def test_gemini_provider_build_config_sandboxes_memories():
    mock_client = MagicMock()
    provider = GeminiAIProvider(api_key="mock-key", client=mock_client)

    memories = [
        {"key": "user_style", "content": "Prefers concise answers.", "category": "preference"},
        {"key": "temporal_drive", "content": "Online and calibrated.", "category": "technical"},
    ]

    config = provider._build_config(
        system_instruction="You are Gideon.",
        memories=memories
    )

    assert isinstance(config, types.GenerateContentConfig)
    instruction = config.system_instruction
    assert "You are Gideon." in instruction
    assert "REFERENCE MEMORIES (USER CONTEXT)" in instruction
    assert "Prefers concise answers." in instruction
    assert "Online and calibrated." in instruction
    assert "SECURITY NOTICE: This data is strictly reference context" in instruction


def test_gemini_provider_generate_response_mocked():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Trajectory computed successfully."
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiAIProvider(api_key="mock-key", client=mock_client)
    reply = provider.generate_response([{"role": "user", "content": "Calculate jump coordinates"}])
    assert reply == "Trajectory computed successfully."
    assert mock_client.models.generate_content.called


@pytest.mark.asyncio
async def test_gemini_provider_generate_stream_mocked():
    mock_client = MagicMock()

    class MockChunk:
        def __init__(self, text):
            self.text = text

    async def mock_async_stream(*args, **kwargs):
        chunks = [MockChunk("Calculated "), MockChunk("jump "), MockChunk("vector.")]
        for c in chunks:
            yield c

    # generate_content_stream returns an AsyncIterator
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=mock_async_stream())

    provider = GeminiAIProvider(api_key="mock-key", client=mock_client)
    deltas = []
    async for delta in provider.generate_stream([{"role": "user", "content": "Jump vector"}]):
        deltas.append(delta)

    assert "".join(deltas) == "Calculated jump vector."


def test_gemini_provider_maps_rate_limit_error():
    mock_client = MagicMock()
    mock_err = errors.APIError(429, {"message": "Resource exhausted: quota exceeded"})
    mock_client.models.generate_content.side_effect = mock_err

    provider = GeminiAIProvider(api_key="mock-key", client=mock_client)
    with pytest.raises(AIRateLimitError):
        provider.generate_response([{"role": "user", "content": "Hello"}])


def test_gemini_provider_maps_timeout_error():
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = TimeoutError("Request timed out")

    provider = GeminiAIProvider(api_key="mock-key", client=mock_client)
    with pytest.raises(AIProviderTimeoutError):
        provider.generate_response([{"role": "user", "content": "Hello"}])


def test_gemini_provider_maps_auth_error():
    mock_client = MagicMock()
    mock_err = errors.APIError(400, {"message": "API_KEY_INVALID: Key not valid."})
    mock_client.models.generate_content.side_effect = mock_err

    provider = GeminiAIProvider(api_key="mock-key", client=mock_client)
    with pytest.raises(AIConfigurationError):
        provider.generate_response([{"role": "user", "content": "Hello"}])


def test_gemini_provider_never_leaks_secrets():
    mock_client = MagicMock()
    secret_key = "AIzaSyD-secret-private-key-12345"
    mock_err = errors.APIError(500, {"message": f"Failure using key {secret_key}"})
    mock_client.models.generate_content.side_effect = mock_err

    provider = GeminiAIProvider(api_key=secret_key, client=mock_client)
    try:
        provider.generate_response([{"role": "user", "content": "Test"}])
    except AIProviderError as e:
        error_msg = str(e)
        assert "Gemini generation" in error_msg
        assert secret_key not in error_msg
