"""Service coordinating assistant capabilities and AI generation."""
from typing import List, Dict, Any, Optional
from app.ai.base import BaseAIProvider
from app.ai.provider_factory import AIProviderFactory
from app.core.config import settings
from app.models.message import Message
from app.schemas.assistant import AssistantStatus


class AssistantService:
    def __init__(self, provider: Optional[BaseAIProvider] = None):
        self.provider = provider or AIProviderFactory.get_provider()

    def get_status(self) -> AssistantStatus:
        return AssistantStatus(
            name=settings.app_name,
            version="1.0.0 (Phase 1)",
            provider=self.provider.name,
            is_demo=self.provider.is_demo,
            model=settings.ai_model if settings.ai_model else "local-demo-engine",
            status="online",
            capabilities=[
                "conversations_persistent",
                "message_history",
                "task_management",
                "offline_demo_provider",
                "database_migrations"
            ],
            unconfigured_features=[
                "real_time_voice_synthesis",
                "wake_word_activation",
                "camera_visual_awareness",
                "computer_automation_actions",
                "calendar_email_integrations"
            ]
        )

    def generate_response(self, context_messages: List[Message]) -> str:
        formatted = [
            {"role": msg.role, "content": msg.content}
            for msg in context_messages
        ]
        return self.provider.generate_response(formatted)
