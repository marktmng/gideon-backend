"""Factory for creating AI provider instances based on application configuration."""
from typing import Optional
from app.ai.base import BaseAIProvider
from app.ai.demo_provider import DemoAIProvider
from app.ai.gemini_provider import GeminiAIProvider
from app.core.config import settings
from app.core.exceptions import AIConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)


class AIProviderFactory:
    """Factory to instantiate AI providers."""

    @staticmethod
    def get_provider(provider_name: Optional[str] = None) -> BaseAIProvider:
        selected = (provider_name or settings.ai_provider or "demo").lower().strip()

        if selected == "demo":
            return DemoAIProvider()

        if selected == "gemini":
            api_key = settings.effective_gemini_api_key
            if not api_key or not api_key.strip():
                raise AIConfigurationError(
                    "Gemini AI provider requested, but no valid API key was found. "
                    "Configure GEMINI_API_KEY in your environment (.env)."
                )
            return GeminiAIProvider(
                api_key=api_key.strip(),
                model=settings.ai_model,
                timeout_seconds=settings.ai_request_timeout_seconds,
                temperature=settings.ai_temperature,
                max_output_tokens=settings.ai_max_output_tokens,
            )

        raise AIConfigurationError(
            f"Unsupported AI provider '{selected}'. Supported providers are: 'demo', 'gemini'."
        )
