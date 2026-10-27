"""Service coordinating assistant capabilities, runtime diagnostics, and AI generation."""
from typing import List, Dict, Any, Optional, AsyncIterator
from app.ai.base import BaseAIProvider
from app.ai.provider_factory import AIProviderFactory
from app.core.config import settings
from app.core.exceptions import AIConfigurationError, AIProviderError
from app.core.logging import get_logger
from app.models.message import Message
from app.schemas.assistant import AssistantStatus

logger = get_logger(__name__)


class AssistantService:
    def __init__(self, provider: Optional[BaseAIProvider] = None):
        self.provider: Optional[BaseAIProvider] = provider
        self.init_error: Optional[str] = None

        if self.provider is None:
            try:
                self.provider = AIProviderFactory.get_provider()
            except AIConfigurationError as err:
                self.init_error = str(err)
                logger.warning("Assistant provider initialization deferred: %s", str(err))

    def _ensure_provider(self) -> BaseAIProvider:
        if self.provider is None:
            if self.init_error:
                raise AIConfigurationError(self.init_error)
            self.provider = AIProviderFactory.get_provider()
        return self.provider

    def get_status(self, db_connected: bool = True) -> AssistantStatus:
        provider_name = self.provider.name if self.provider else (settings.ai_provider or "unknown")
        is_demo = self.provider.is_demo if self.provider else (provider_name == "demo")
        has_credentials = bool(settings.effective_gemini_api_key and settings.effective_gemini_api_key.strip())
        streaming_supported = self.provider.supports_streaming if self.provider else False

        if not self.provider and self.init_error:
            system_status = "unconfigured"
        elif is_demo:
            system_status = "demo_mode"
        elif has_credentials:
            system_status = "configured"
        else:
            system_status = "unconfigured"

        return AssistantStatus(
            name=settings.app_name,
            version="3.0.0 (Phase 3)",
            provider=provider_name,
            is_demo=is_demo,
            model=settings.ai_model if settings.ai_model else "local-demo-engine",
            status=system_status,
            has_provider_credentials=has_credentials,
            streaming_supported=streaming_supported,
            memory_enabled=True,
            database_connected=db_connected,
            provider_initialized=self.provider is not None,
            capabilities=[
                "conversations_persistent",
                "message_history",
                "context_aware_generation",
                "streaming_responses",
                "persistent_memory_retrieval",
                "task_management",
                "google_gemini_provider",
                "offline_demo_provider",
                "database_migrations",
                "voice_speech_interaction",
                "camera_vision_service",
                "hand_gesture_recognition",
                "futuristic_tech_brain_ui",
            ],
            unconfigured_features=[
                "wake_word_continuous_activation",
                "computer_desktop_automation",
                "calendar_email_integrations",
                "biometric_facial_identification",
            ],
        )

    def generate_response(
        self,
        context_messages: List[Message],
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        provider = self._ensure_provider()
        formatted = [
            {"role": msg.role, "content": msg.content}
            for msg in context_messages
        ]
        return provider.generate_response(messages=formatted, memories=memories)

    async def generate_response_async(
        self,
        context_messages: List[Message],
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        provider = self._ensure_provider()
        formatted = [
            {"role": msg.role, "content": msg.content}
            for msg in context_messages
        ]
        return await provider.generate_response_async(messages=formatted, memories=memories)

    async def generate_stream(
        self,
        context_messages: List[Message],
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        provider = self._ensure_provider()
        formatted = [
            {"role": msg.role, "content": msg.content}
            for msg in context_messages
        ]
        async for chunk in provider.generate_stream(messages=formatted, memories=memories):
            yield chunk
