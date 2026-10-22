"""Factory for creating AI provider instances based on application configuration."""
from app.ai.base import BaseAIProvider
from app.ai.demo_provider import DemoAIProvider
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AIProviderFactory:
    """Factory to instantiate AI providers."""

    @staticmethod
    def get_provider(provider_name: str | None = None) -> BaseAIProvider:
        selected = (provider_name or settings.ai_provider or "demo").lower().strip()

        if selected == "demo":
            return DemoAIProvider()

        # Clean extension point for future providers (e.g. OpenAI, Anthropic, Gemini)
        logger.warning(
            "Provider '%s' is not yet implemented or configured. Falling back to DemoAIProvider.",
            selected
        )
        return DemoAIProvider()
